from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from copy import deepcopy
import json
import re
from typing import Any, Callable

from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS
from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver
from nexterp_agent.master_data import MasterDataRelease

from .candidate_inventory import enrich_item_entity_results
from .deepseek_material_request import DeepSeekSettings, call_deepseek_json
from .resolvers import EntityResolverRegistry, ResolutionResult
from .session import RuntimeSessionState, RuntimeSessionStore
from .tool_access import ToolExposure, make_tool_access_policy
from .tool_contracts import ToolContract, build_tool_contracts
from .tool_gateway import ToolGateway, ToolSession


MAX_AGENT_STEPS = 10
MAX_MODEL_RETRIES = 1
MAX_TOOL_REPAIRS = 2
AGENT_ACTIONS = frozenset({"discover_tools", "get_tool_contracts", "resolve_entities", "execute_tool", "ask_user", "finish"})
MODULE_DESCRIPTIONS = {
    "generic": "通用文档、评论、待办和附件",
    "users": "用户、角色和权限",
    "assets": "固定资产、折旧、维护和移动",
    "stock": "库存、仓库、收发、调拨、批次和序列号",
    "buying": "材料申请、询价、供应商、采购订单和采购收货",
    "accounting": "应收应付、发票、付款、总账和财务报表",
    "projects": "项目成本、项目领料和任务",
}
SENSITIVE_ENTITY_FIELDS = {
    "item_code": "item",
    "project": "project",
    "warehouse": "warehouse",
    "source_warehouse": "warehouse",
    "target_warehouse": "warehouse",
    "supplier": "supplier",
    "company": "company",
    "document_name": "document",
    "assigned_to": "employee",
    "user": "employee",
}

Planner = Callable[[list[dict[str, str]]], dict[str, Any]]
ClientFactory = Callable[[str], ERPNextClient]


@dataclass(frozen=True)
class DeepSeekTurnResult:
    status: str
    message: str
    steps: tuple[dict[str, Any], ...] = ()
    pending_tool_call: dict[str, Any] | None = None
    tool_call: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    tool_calls: tuple[dict[str, Any], ...] = ()
    tool_results: tuple[dict[str, Any], ...] = ()
    questions: tuple[str, ...] = ()
    candidates: tuple[dict[str, Any], ...] = ()
    intent: dict[str, Any] | None = None
    resolutions: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_agent_action(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("DeepSeek action must be a JSON object")
    action = payload.get("action")
    if action not in AGENT_ACTIONS:
        raise ValueError(f"Unsupported DeepSeek action: {action}")
    if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
        payload["summary"] = f"DeepSeek请求执行{action}"
    if not isinstance(payload.get("arguments") or {}, dict):
        raise ValueError("DeepSeek action arguments must be an object")
    arguments = payload.get("arguments") or {}
    if action == "discover_tools" and not str(arguments.get("query") or "").strip():
        raise ValueError("discover_tools.arguments.query is required")
    if action == "get_tool_contracts" and (not isinstance(arguments.get("tool_names"), list) or not arguments["tool_names"]):
        raise ValueError("get_tool_contracts.arguments.tool_names must be a non-empty array")
    if action == "resolve_entities" and (not isinstance(arguments.get("entities"), list) or not arguments["entities"]):
        raise ValueError("resolve_entities.arguments.entities must be a non-empty array")
    if action == "execute_tool" and not isinstance(arguments.get("tool_call"), dict):
        raise ValueError("execute_tool.arguments.tool_call is required")
    if action == "ask_user" and (not isinstance(arguments.get("questions"), list) or not arguments["questions"]):
        raise ValueError("ask_user.arguments.questions must be a non-empty array")
    if action == "finish" and not str(arguments.get("message") or "").strip():
        raise ValueError("finish.arguments.message is required")
    return payload


class ToolDiscoveryIndex:
    def __init__(self, contracts: list[ToolContract] | None = None) -> None:
        self.contracts = contracts or build_tool_contracts()

    def discover(self, query: str, *, policy, modules: list[str] | None = None, limit: int = 8) -> list[dict[str, Any]]:
        module_filter = {str(value) for value in modules or [] if value in MODULE_DESCRIPTIONS}
        query_tokens = _tokens(query)
        scored: list[tuple[int, ToolContract]] = []
        for contract in self.contracts:
            module = _tool_module(contract.name)
            if module_filter and module not in module_filter:
                continue
            if contract.expose is not ToolExposure.AGENT_VISIBLE or not policy.decide(contract.name, origin="agent").allowed:
                continue
            haystack = f"{contract.name} {contract.purpose} {' '.join(contract.business_contract)}".lower()
            score = sum(3 if token in contract.name.lower() else 1 for token in query_tokens if token in haystack)
            if module_filter:
                score += 1
            scored.append((score, contract))
        scored.sort(key=lambda row: (-row[0], row[1].name))
        return [_compact_contract(contract) for _, contract in scored[: max(1, min(limit, 8))]]

    def full_contracts(self, names: list[str], *, policy) -> list[dict[str, Any]]:
        wanted = list(dict.fromkeys(str(name) for name in names))[:5]
        contracts = {contract.name: contract for contract in self.contracts}
        result = []
        for name in wanted:
            contract = contracts.get(name)
            if not contract or contract.expose is not ToolExposure.AGENT_VISIBLE or not policy.decide(name, origin="agent").allowed:
                continue
            result.append(_full_contract(contract))
        return result


class DeepSeekAgentRuntime:
    def __init__(
        self,
        *,
        release: MasterDataRelease | None = None,
        planner: Planner | None = None,
        deepseek_settings: DeepSeekSettings | None = None,
        client_factory: ClientFactory | None = None,
        session_store: RuntimeSessionStore | None = None,
        max_steps: int = MAX_AGENT_STEPS,
    ) -> None:
        self.release = release or MasterDataRelease()
        self.planner = planner
        self.deepseek_settings = deepseek_settings
        self.client_factory = client_factory
        self.session_store = session_store or RuntimeSessionStore()
        self.entity_resolvers = EntityResolverRegistry(self.release)
        self.material_resolver = ReleaseMaterialResolver(self.release.material_release_path)
        self.materials_by_code = {row["item_code"]: row for row in self.release.materials if row.get("item_code")}
        self.discovery = ToolDiscoveryIndex()
        self.max_steps = max_steps

    def run_once(
        self,
        user_text: str,
        *,
        user: str,
        execute: bool = False,
        today: date | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> DeepSeekTurnResult:
        employee = self._employee_for_user(user)
        profile = self._profile_for_employee(employee)
        session = self.session_store.load(user, profile=profile)
        if not session.company:
            session.company = self.release.company_name("STEC")
        if request_id and request_id in session.idempotency_results:
            return _result_from_dict(session.idempotency_results[request_id])

        selected_context = dict(context or {})
        if selected_context.get("project_code"):
            session.selected_project_code = str(selected_context["project_code"])
        if selected_context.get("warehouse"):
            session.selected_warehouse_name = str(selected_context["warehouse"])
        policy = make_tool_access_policy(profile)
        steps: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        confirmed_call: dict[str, Any] | None = None
        today = today or date.today()

        if execute:
            pending = session.pending_action
            if not isinstance(pending, dict) or not isinstance(pending.get("tool_call"), dict):
                return self._save(session, user_text, DeepSeekTurnResult("failed", "没有等待确认的ToolCall。"), request_id)
            call = pending["tool_call"]
            confirmed_call = deepcopy(call)
            contract = next((item for item in self.discovery.contracts if item.name == call.get("tool")), None)
            if contract and contract.confirm != "none":
                _attach_runtime_confirmation(call, user=user, reason=str(pending.get("user_text") or user_text))
            execution = self._execute(call, user=user, profile=profile)
            payload = execution.to_dict()
            tool_results.append(payload)
            steps.extend(pending.get("steps") or [])
            observations.extend(pending.get("observations") or [])
            steps.append(_step("ERPNext执行", "execute_tool", call, payload))
            session.pending_action = None
            self._remember_result(session, payload)
            if not execution.ok and execution.error_type in {"permission_error", "auth_error"}:
                result = DeepSeekTurnResult("failed", execution.user_message or execution.error or "ERPNext拒绝执行。", tuple(steps), tool_result=payload, tool_results=tuple(tool_results))
                return self._save(session, user_text, result, request_id)
            observations.append({"type": "tool_result", "tool_call": call, "result": _safe_tool_result(payload)})

        planner_step_count = sum(1 for step in steps if step.get("label") == "DeepSeek规划")
        for _ in range(max(0, self.max_steps - planner_step_count)):
            prompt = self._messages(user_text, employee, session, today, observations, steps)
            try:
                action = self._plan_with_retry(prompt)
            except Exception as exc:
                if confirmed_call is not None and tool_results and tool_results[-1].get("ok"):
                    steps.append(_step(
                        "生成回复降级",
                        "finish_fallback",
                        {"error": str(exc)},
                        {"source": "successful_tool_result"},
                    ))
                    result = DeepSeekTurnResult(
                        "completed",
                        _successful_execution_message(tool_results[-1]),
                        tuple(steps),
                        tool_result=tool_results[-1],
                        tool_results=tuple(tool_results),
                    )
                    return self._save(session, user_text, result, request_id)
                result = DeepSeekTurnResult("failed", f"DeepSeek规划失败：{exc}", tuple(steps), tool_results=tuple(tool_results))
                return self._save(session, user_text, result, request_id)
            steps.append(_step("DeepSeek规划", action["action"], action.get("arguments") or {}, {"summary": action["summary"]}))
            kind = action["action"]
            arguments = action.get("arguments") or {}

            if kind == "discover_tools":
                cards = self.discovery.discover(str(arguments.get("query") or user_text), policy=policy, modules=arguments.get("modules"), limit=int(arguments.get("limit") or 8))
                observation = {"type": kind, "tools": cards}
                steps.append(_step("发现工具", kind, arguments, observation))
                observations.append(observation)
                continue
            if kind == "get_tool_contracts":
                contracts = self.discovery.full_contracts(arguments.get("tool_names") or [], policy=policy)
                observation = {"type": kind, "contracts": contracts}
                steps.append(_step("读取契约", kind, arguments, observation))
                observations.append(observation)
                continue
            if kind == "resolve_entities":
                observation = self._resolve_entities(arguments, user=user, today=today, session=session)
                steps.append(_step("解析实体", kind, arguments, observation))
                observations.append(observation)
                resolved_values = _resolved_entity_values(observation)
                if any(entity.get("kind") == "item" for entity in observation.get("entities") or []):
                    for selected_id, selected in list(session.selected_entities.items()):
                        if selected.get("kind") == "item":
                            session.selected_entities.pop(selected_id, None)
                for entity in observation.get("entities") or []:
                    entity_id = str(entity.get("id") or "")
                    if entity_id and entity_id not in resolved_values:
                        session.selected_entities.pop(entity_id, None)
                session.selected_entities.update(resolved_values)
                recommended_tools = _document_next_action_tools(observation)
                if recommended_tools:
                    contracts = self.discovery.full_contracts(recommended_tools, policy=policy)
                    contract_observation = {"type": "get_tool_contracts", "contracts": contracts}
                    steps.append(_step(
                        "自动读取状态契约",
                        "get_tool_contracts",
                        {"tool_names": recommended_tools},
                        contract_observation,
                    ))
                    observations.append(contract_observation)
                continue
            if kind == "ask_user":
                questions = tuple(str(value) for value in arguments.get("questions") or [] if str(value).strip())
                if not questions:
                    questions = (str(arguments.get("question") or "请补充必要信息。"),)
                candidates = tuple(_hydrate_presented_candidates(arguments.get("candidates") or [], observations))
                message = str(arguments.get("message") or "\n\n".join(questions))
                result = DeepSeekTurnResult("needs_clarification", message, tuple(steps), questions=questions, candidates=candidates, tool_results=tuple(tool_results))
                session.pending_action = {"type": "clarification", "steps": steps, "observations": observations}
                return self._save(session, user_text, result, request_id)
            if kind == "execute_tool":
                call = deepcopy(arguments.get("tool_call") or arguments)
                contract = next((item for item in self.discovery.contracts if item.name == call.get("tool")), None) if isinstance(call, dict) else None
                if (
                    contract
                    and contract.expose is ToolExposure.AGENT_VISIBLE
                    and policy.decide(contract.name, origin="agent").allowed
                    and contract.name not in _loaded_contract_names(observations)
                ):
                    observation = {"type": "get_tool_contracts", "contracts": [_full_contract(contract)]}
                    steps.append(_step(
                        "自动读取契约",
                        "get_tool_contracts",
                        {"tool_names": [contract.name]},
                        observation,
                    ))
                    observations.append(observation)
                    continue
                corrections: list[dict[str, Any]] = []
                if contract:
                    corrections = _inject_resolved_arguments(call["arguments"], contract, session, observations)
                    corrections.extend(_inject_source_document_references(call, session, observations))
                    corrections.extend(_inject_material_request_reference_prices(call, self.materials_by_code))
                    if corrections:
                        steps.append(_step("参数编排", "inject_context", {}, {"corrections": corrections}))
                if _same_business_call(confirmed_call, call) and tool_results and tool_results[-1].get("ok"):
                    steps.append(_step("跳过重复动作", kind, call, {"reason": "confirmed_tool_call_already_succeeded"}))
                    result = DeepSeekTurnResult(
                        "completed",
                        _successful_execution_message(tool_results[-1]),
                        tuple(steps),
                        tool_result=tool_results[-1],
                        tool_results=tuple(tool_results),
                    )
                    return self._save(session, user_text, result, request_id)
                validation_error = self._validate_proposed_call(
                    call,
                    user=user,
                    policy=policy,
                    session=session,
                    observations=observations,
                )
                if validation_error:
                    observations.append({"type": "tool_validation_error", "error": validation_error, "tool_call": call})
                    if sum(1 for item in observations if item.get("type") == "tool_validation_error") > MAX_TOOL_REPAIRS:
                        result = DeepSeekTurnResult("failed", validation_error, tuple(steps), tool_calls=(call,) if isinstance(call, dict) else (), tool_results=tuple(tool_results))
                        return self._save(session, user_text, result, request_id)
                    continue
                contract = next(contract for contract in self.discovery.contracts if contract.name == call["tool"])
                if contract.confirm != "none":
                    session.pending_action = {"tool_call": call, "steps": steps, "observations": observations, "user_text": user_text}
                    result = DeepSeekTurnResult(
                        "needs_confirmation",
                        _pending_confirmation_message(action["summary"]),
                        tuple(steps),
                        pending_tool_call=call,
                        tool_call=call,
                        tool_calls=(call,),
                        tool_results=tuple(tool_results),
                    )
                    return self._save(session, user_text, result, request_id=None)
                execution = self._execute(call, user=user, profile=profile)
                payload = execution.to_dict()
                tool_results.append(payload)
                steps.append(_step("ERPNext执行", kind, call, payload))
                self._remember_result(session, payload)
                if not execution.ok and execution.error_type in {"permission_error", "auth_error"}:
                    result = DeepSeekTurnResult("failed", execution.user_message or execution.error or "ERPNext拒绝执行。", tuple(steps), tool_call=call, tool_result=payload, tool_calls=(call,), tool_results=tuple(tool_results))
                    return self._save(session, user_text, result, request_id)
                observations.append({"type": "tool_result", "tool_call": call, "result": _safe_tool_result(payload)})
                continue
            if kind == "finish":
                message = str(arguments.get("message") or action["summary"])
                result = DeepSeekTurnResult("completed", message, tuple(steps), tool_result=tool_results[-1] if tool_results else None, tool_results=tuple(tool_results))
                return self._save(session, user_text, result, request_id)

        if confirmed_call is not None and tool_results and tool_results[-1].get("ok"):
            steps.append(_step(
                "生成回复降级",
                "finish_fallback",
                {"reason": "planner_step_limit_after_success"},
                {"source": "successful_tool_result"},
            ))
            result = DeepSeekTurnResult(
                "completed",
                _successful_execution_message(tool_results[-1]),
                tuple(steps),
                tool_result=tool_results[-1],
                tool_results=tuple(tool_results),
            )
            return self._save(session, user_text, result, request_id)
        result = DeepSeekTurnResult("failed", f"Agent达到{self.max_steps}步规划上限，已停止执行。", tuple(steps), tool_results=tuple(tool_results))
        return self._save(session, user_text, result, request_id)

    def _messages(self, user_text: str, employee: dict[str, str], session: RuntimeSessionState, today: date, observations: list[dict[str, Any]], steps: list[dict[str, Any]]) -> list[dict[str, str]]:
        system = (
            "你是ERPNext企业员工自主Agent。你必须通过JSON动作逐步工作，不得输出动作之外的正文。"
            "summary只用于审计，不会展示给员工；ask_user.message和finish.message必须像一名懂业务的工作助理，"
            "先简短说明你已理解和查到了什么，再提出员工能直接回答的问题，禁止使用‘询问数量’之类流程节点措辞。"
            "你不能猜测ERPNext主键；物料、项目、仓库、供应商、公司、员工和单据号必须先resolve_entities，"
            "或来自runtime_context中已经确认的数据。先discover_tools，再get_tool_contracts，拿到契约后才能execute_tool。"
            "只读工具可直接执行；写工具会由Runtime暂停并要求用户确认。候选不唯一时ask_user。"
            "用户明确要求写操作时，不要再用ask_user口头确认，也不要自行填写confirmation；直接生成业务ToolCall，"
            "Runtime会展示业务摘要并在用户点击确认执行时生成审计确认元数据，确保员工只确认一次。"
            "单据启用ERPNext Workflow时，禁止使用任何submit_document工具；必须先执行erpnext.get_workflow_actions，"
            "再使用erpnext.apply_workflow执行当前账号真实可用的动作。反之，实时单据快照没有workflow_state且docstatus=0时，"
            "说明该单据未启用工作流：禁止调用get_workflow_actions或apply_workflow，必须发现并使用所属模块的submit_document工具。"
            "会话中的历史单号只能作为候选线索；对‘刚才的单据’或任何后续单据操作，必须重新resolve_entities(kind=document)"
            "读取ERPNext实时快照后再规划，禁止沿用旧对话中的状态。用户已经明确说出询价、下单、收货或退货时，"
            "不得再反问要做哪一种操作；应先发现并读取对应工具契约，只追问契约真正缺少的业务信息。"
            "物料解析结果会自动附带候选SKU在各仓库的实时库存；必须结合候选匹配度和库存分布比较推荐，"
            "当物料resolution.selection_required为true，或存在多个用途/规格/单位不同的相关SKU时，必须ask_user，"
            "并在message或questions中列出最多5个相关候选的SKU名称、编码、关键规格、单位和各仓可用库存；"
            "同时合并追问数量等其他缺失信息，不得只问数量，也不得列出名称仅包含查询词但不是同一种物料的候选。"
            "不得再次逐个查询这些候选的库存。用户明确说出物料需求数量和单位时，"
            "resolve_entities中的对应item必须填写qty和uom，不得省略。"
            "完成后finish，并只引用observation中的真实数字、状态和单号。不要展示隐藏思维过程。"
            "必须严格使用action_schemas中给出的字段名，不得用type/value/materials/items等替代entities中的kind/query。"
        )
        protocol = {
            "action_schema": {"action": "discover_tools | get_tool_contracts | resolve_entities | execute_tool | ask_user | finish", "summary": "可审计的简短动作说明", "arguments": "必须符合对应action_schemas"},
            "action_schemas": {
                "discover_tools": {"query": "描述所需业务能力，必填", "modules": ["generic | users | assets | stock | buying | accounting | projects"], "limit": "1-8"},
                "get_tool_contracts": {"tool_names": ["从discover_tools结果逐字复制的工具名，最多5个"]},
                "resolve_entities": {"entities": [{"id": "本轮唯一标识", "kind": "item | project | warehouse | supplier | company | employee | date | uom | document", "query": "用户原话或待核对主键", "specs": {}, "qty": "kind=item时可提供需求数量", "uom": "kind=item时可提供用户单位", "doctype": "kind=document时必填"}]},
                "execute_tool": {"tool_call": {"tool": "已读取契约的工具名", "arguments": {}}},
                "ask_user": {"message": "可直接展示给员工的自然回复", "questions": ["员工可直接回答的最少必要问题"], "candidates": ["从observation复制的相关候选，可省略并由Runtime补齐"]},
                "finish": {"message": "基于真实observation的最终答复"},
            },
            "modules": MODULE_DESCRIPTIONS,
            "runtime_context": {
                "current_date": today.isoformat(), "employee": employee, "profile": session.profile,
                "company": session.company, "selected_project_code": session.selected_project_code,
                "selected_warehouse_name": session.selected_warehouse_name,
                "confirmed_entities": session.selected_entities, "documents": session.documents,
                "recent_turns": session.turns[-6:],
            },
            "observations": observations[-12:],
            "step_count": len(steps),
        }
        return [{"role": "system", "content": system}, {"role": "system", "content": json.dumps(protocol, ensure_ascii=False)}, {"role": "user", "content": user_text}]

    def _plan_with_retry(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        error: Exception | None = None
        attempt_messages = list(messages)
        for _ in range(MAX_MODEL_RETRIES + 1):
            try:
                payload = self.planner(attempt_messages) if self.planner else call_deepseek_json(attempt_messages, settings=self.deepseek_settings)
                return validate_agent_action(payload)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                error = exc
                attempt_messages.append({"role": "system", "content": f"上一次输出不符合动作协议：{exc}。请只返回合法JSON动作。"})
        raise ValueError(str(error))

    def _resolve_entities(
        self,
        arguments: dict[str, Any],
        *,
        user: str,
        today: date,
        session: RuntimeSessionState,
    ) -> dict[str, Any]:
        entities = arguments.get("entities") or []
        results = []
        for entity in entities[:20]:
            entity_id = str(entity.get("id") or len(results) + 1)
            kind = str(entity.get("kind") or "")
            query = entity.get("query")
            if kind == "item":
                resolution = self.material_resolver.resolve(str(query or ""), specs=entity.get("specs") or {}, limit=5)
                resolution = _require_selection_for_shared_item_name(
                    resolution,
                    query=str(query or ""),
                    specs=entity.get("specs") or {},
                )
                results.append({
                    "id": entity_id,
                    "kind": kind,
                    "query": query,
                    "requested_qty": entity.get("qty"),
                    "requested_uom": entity.get("uom"),
                    "resolution": resolution,
                })
                continue
            if kind == "document":
                doctype = str(entity.get("doctype") or "").strip()
                name = str(query or "").strip()
                if not doctype or not name or self.client_factory is None:
                    resolution = {"status": "needs_clarification", "question": "请同时说明单据类型和单号。"}
                else:
                    lookup = self.client_factory(user).get_document(doctype, name)
                    resolution = (
                        {
                            "status": "resolved",
                            "value": name,
                            "label": name,
                            "confidence": 1.0,
                            "reason": "ERPNext单据精确核对并读取实时状态",
                            "row": _compact_document_snapshot(lookup.data),
                        }
                        if lookup.ok and isinstance(lookup.data, dict)
                        else {
                            "status": "not_found",
                            "question": f"没有找到或无权访问{doctype} {name}。",
                            "reason": lookup.user_message or lookup.error,
                        }
                    )
                results.append({"id": entity_id, "kind": kind, "query": query, "resolution": resolution})
                continue
            try:
                resolution = self.entity_resolvers.resolve(kind, query, current_date=today)
                if kind == "project":
                    resolution = self._live_project(user, resolution)
                results.append({"id": entity_id, "kind": kind, "query": query, "resolution": resolution.to_dict()})
            except KeyError:
                results.append({"id": entity_id, "kind": kind, "query": query, "resolution": {"status": "unsupported", "question": f"不支持的实体类型：{kind}"}})
        inventory_query = {"status": "skipped", "reason": "没有物料候选或ERPNext客户端不可用。"}
        if self.client_factory is not None and any(result.get("kind") == "item" for result in results):
            inventory_query = enrich_item_entity_results(
                results,
                client=self.client_factory(user),
                preferred_warehouse=self._preferred_inventory_warehouse(session),
                related_warehouses=self._related_inventory_warehouses(session),
            )
        return {"type": "resolve_entities", "entities": results, "inventory_query": inventory_query}

    def _preferred_inventory_warehouse(self, session: RuntimeSessionState) -> str | None:
        selected = str(session.selected_warehouse_name or "").strip()
        if selected:
            for warehouse in self.release.warehouses.values():
                if selected in {
                    warehouse.get("warehouse_code"),
                    warehouse.get("warehouse_name"),
                    warehouse.get("erpnext_warehouse_name"),
                }:
                    return warehouse.get("erpnext_warehouse_name") or selected
            return selected
        project = self.release.projects.get(str(session.selected_project_code or ""))
        if not project:
            return None
        warehouse = self.release.warehouses.get(project.get("default_warehouse_code", ""))
        return warehouse.get("erpnext_warehouse_name") if warehouse else None

    def _related_inventory_warehouses(self, session: RuntimeSessionState) -> list[str]:
        preferred = self._preferred_inventory_warehouse(session)
        related = [preferred] if preferred else []
        for warehouse in self.release.warehouses.values():
            if warehouse.get("status") != "active":
                continue
            if warehouse.get("warehouse_code") == "WH-WCL-BASE":
                name = warehouse.get("erpnext_warehouse_name")
                if name and name not in related:
                    related.append(name)
        return related

    def _validate_proposed_call(
        self,
        call: Any,
        *,
        user: str,
        policy,
        session: RuntimeSessionState,
        observations: list[dict[str, Any]],
    ) -> str | None:
        if not isinstance(call, dict) or not isinstance(call.get("tool"), str) or not isinstance(call.get("arguments") or {}, dict):
            return "ToolCall必须包含tool和arguments。"
        names = {contract.name: contract for contract in self.discovery.contracts}
        contract = names.get(call["tool"])
        if not contract or contract.expose is not ToolExposure.AGENT_VISIBLE:
            return "该工具未向Agent开放。"
        decision = policy.decide(call["tool"], origin="agent")
        if not decision.allowed:
            return f"当前岗位不能使用工具：{call['tool']}。"
        loaded_contracts = _loaded_contract_names(observations)
        if call["tool"] not in loaded_contracts:
            return f"执行前必须先读取工具契约：{call['tool']}。"
        schema = next(schema for schema in ERPNext_TOOL_SCHEMAS if schema["name"] == call["tool"])["parameters"]
        validation_arguments = deepcopy(call["arguments"])
        if contract.confirm != "none" and "confirmation" in schema.get("properties", {}) and not validation_arguments.get("confirmation"):
            validation_arguments["confirmation"] = _runtime_confirmation(user=user, reason="等待用户在Runtime确认")
        schema_error = _validate_json_value(validation_arguments, schema, "arguments")
        if schema_error:
            return schema_error
        if call["tool"].endswith(".submit_document") and self.client_factory is not None:
            doctype = str(call["arguments"].get("doctype") or "")
            name = str(call["arguments"].get("name") or "")
            if doctype and name:
                detail = self.client_factory(user).get_document(doctype, name)
                if detail.ok and isinstance(detail.data, dict) and str(detail.data.get("workflow_state") or "").strip():
                    return (
                        f"{doctype} {name} 已启用ERPNext工作流，不能使用{call['tool']}。"
                        "请先读取erpnext.get_workflow_actions，再通过erpnext.apply_workflow执行当前账号可用动作。"
                    )
        allowed = _allowed_entity_values(session, observations)
        for key, value in _walk_arguments(call["arguments"]):
            kind = SENSITIVE_ENTITY_FIELDS.get(key)
            if kind and value not in (None, "") and str(value) not in allowed.get(kind, set()):
                return f"参数{key}={value}不是Resolver或会话确认的真实值，请先resolve_entities。"
        return None

    def _execute(self, call: dict[str, Any], *, user: str, profile: str):
        if self.client_factory is None:
            raise RuntimeError("ERPNext client factory is required for execution")
        policy = make_tool_access_policy(profile)
        gateway = ToolGateway(ERPNextAdapter(self.client_factory(user)), ToolSession(user=user, policy=policy, verify_erpnext_identity=True))
        return gateway.execute(call, origin="agent")

    def _live_project(self, user: str, resolution: ResolutionResult) -> ResolutionResult:
        if resolution.status != "resolved" or not resolution.value or self.client_factory is None:
            return resolution
        project = self.release.projects.get(resolution.value)
        if not project:
            return resolution
        result = self.client_factory(user).search_documents("Project", filters={"project_name": project["project_name"]}, fields=["name", "project_name"], limit=2)
        if not result.ok or not isinstance(result.data, list) or len(result.data) != 1:
            return ResolutionResult("needs_selection", candidates=(), question="ERPNext中没有找到唯一项目，请核对项目主数据。")
        return ResolutionResult("resolved", result.data[0]["name"], project["project_short_name"], 1.0, reason="ERPNext项目主键已核对")

    def _remember_result(self, session: RuntimeSessionState, payload: dict[str, Any]) -> None:
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        document = data.get("document") if isinstance(data.get("document"), dict) else data
        doctype, name = document.get("doctype"), document.get("name")
        if doctype and name:
            session.remember_document(str(doctype), str(name))

    def _employee_for_user(self, user: str) -> dict[str, str]:
        for row in self.release.employees.values():
            if row.get("user_email") == user:
                return row
        raise KeyError(f"Employee not found for user: {user}")

    @staticmethod
    def _profile_for_employee(employee: dict[str, str]) -> str:
        return {"ROLE-GM": "manager", "ROLE-MAT-EQP-MGR": "procurement", "ROLE-OPS-MGR": "manager", "ROLE-PROJ-MGR": "project", "ROLE-TECH-LEAD": "project", "ROLE-MATERIAL-CLERK": "project", "ROLE-SYSADMIN": "system_admin"}.get(employee["role_code"], "project")

    def _save(self, session: RuntimeSessionState, user_text: str, result: DeepSeekTurnResult, request_id: str | None) -> DeepSeekTurnResult:
        payload = result.to_dict()
        if request_id and result.status in {"completed", "failed"}:
            session.remember_request(request_id, payload)
        session.agent_steps = list(result.steps)
        session.add_turn({"user_text": user_text, "result": payload})
        self.session_store.save(session)
        return result


def _tool_module(name: str) -> str:
    parts = name.split(".")
    return parts[1] if len(parts) > 2 else "generic"


def _compact_contract(contract: ToolContract) -> dict[str, Any]:
    return {"name": contract.name, "purpose": contract.purpose, "risk_level": contract.risk_level, "confirm": contract.confirm, "module": _tool_module(contract.name)}


def _full_contract(contract: ToolContract) -> dict[str, Any]:
    return {"name": contract.name, "purpose": contract.purpose, "risk_level": contract.risk_level, "confirm": contract.confirm, "business_contract": list(contract.business_contract), "parameters": [asdict(param) for param in contract.parameters]}


def _loaded_contract_names(observations: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("name"))
        for observation in observations
        if observation.get("type") == "get_tool_contracts"
        for item in observation.get("contracts") or []
        if item.get("name")
    }


def _tokens(value: str) -> list[str]:
    text = str(value).lower()
    tokens = re.findall(r"[a-z0-9_.]+", text)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run[index:index + size] for size in (2, 3, 4) for index in range(max(0, len(run) - size + 1)))
    return list(dict.fromkeys(token for token in tokens if token))


def _step(label: str, action: str, payload: Any, result: Any) -> dict[str, Any]:
    return {"label": label, "action": action, "payload": payload, "result": result}


def _safe_tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    safe = {key: value for key, value in payload.items() if key not in {"debug"}}
    if isinstance(safe.get("data"), list):
        safe["row_count"] = len(safe["data"])
    return safe


def _successful_execution_message(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    doctype = str(data.get("doctype") or "ERPNext单据")
    name = str(data.get("name") or "").strip()
    status = str(data.get("workflow_state") or data.get("status") or "").strip()
    target = f"{doctype} {name}".strip()
    return f"{target} 已执行成功" + (f"，当前状态：{status}。" if status else "。")


def _pending_confirmation_message(summary: str) -> str:
    action = str(summary or "执行这项操作").strip().rstrip("。")
    return f"我已准备好{action}，但尚未写入 ERPNext。请确认后再执行。"


def _runtime_confirmation(*, user: str, reason: str) -> dict[str, Any]:
    return {
        "confirmed": True,
        "confirmed_by": user,
        "confirmed_at": datetime.now().astimezone().isoformat(),
        "confirmation_text": "用户通过员工工作台明确确认执行",
        "reason": reason.strip() or "执行已确认的业务操作",
    }


def _attach_runtime_confirmation(call: dict[str, Any], *, user: str, reason: str) -> None:
    arguments = call.get("arguments")
    if isinstance(arguments, dict):
        arguments["confirmation"] = _runtime_confirmation(user=user, reason=reason)


def _same_business_call(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    left_copy = deepcopy(left)
    right_copy = deepcopy(right)
    for value in (left_copy, right_copy):
        arguments = value.get("arguments")
        if isinstance(arguments, dict):
            arguments.pop("confirmation", None)
    return left_copy == right_copy


def _require_selection_for_shared_item_name(
    resolution: dict[str, Any],
    *,
    query: str,
    specs: dict[str, Any],
) -> dict[str, Any]:
    """Do not auto-select one SKU when the user supplied only a shared item name."""
    if specs or resolution.get("status") not in {"ready", "needs_confirmation", "needs_clarification"}:
        return resolution
    normalized_query = _normalized_item_text(query)
    candidates = resolution.get("candidates") or []
    same_name = [
        candidate
        for candidate in candidates
        if _normalized_item_text(str(candidate.get("item_name") or "")) == normalized_query
    ]
    if len({str(candidate.get("item_code") or "") for candidate in same_name if candidate.get("item_code")}) < 2:
        return resolution
    updated = deepcopy(resolution)
    updated["status"] = "needs_clarification"
    updated["selection_required"] = True
    updated["recommended"] = updated.get("resolved")
    updated["resolved"] = None
    updated["candidates"] = same_name
    updated["questions"] = [f"“{query}”对应多个规格，请先选择具体物料。"]
    updated["decision_reason"] = "用户输入的是多个SKU共用的物料名称，不能仅凭检索分数自动选择。"
    return updated


def _normalized_item_text(value: str) -> str:
    return re.sub(r"[\s\-_()/（）]+", "", value).lower()


def _resolved_entity_values(observation: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for entity in observation.get("entities") or []:
        resolution = entity.get("resolution") or {}
        if resolution.get("status") in {"resolved", "ready"}:
            value = resolution.get("value") or (resolution.get("resolved") or {}).get("item_code")
            if value:
                values[entity["id"]] = {
                    "kind": entity["kind"],
                    "value": value,
                    "label": resolution.get("label"),
                    "row": resolution.get("row") or resolution.get("resolved"),
                }
    return values


def _compact_document_snapshot(document: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "doctype", "name", "title", "owner", "docstatus", "status", "workflow_state",
        "company", "supplier", "material_request_type", "transaction_date", "schedule_date", "modified",
    )
    snapshot = {field: document.get(field) for field in fields if document.get(field) not in (None, "")}
    if int(document.get("docstatus") or 0) == 0:
        if str(document.get("workflow_state") or "").strip():
            snapshot["allowed_next_actions"] = ["erpnext.get_workflow_actions", "erpnext.apply_workflow"]
        else:
            submit_tool = _submit_tool_for_doctype(str(document.get("doctype") or ""))
            if submit_tool:
                snapshot["allowed_next_actions"] = [submit_tool]
    rows = document.get("items")
    if isinstance(rows, list):
        item_fields = (
            "name", "item_code", "item_name", "qty", "uom", "stock_uom", "warehouse", "project",
            "rate", "amount", "ordered_qty", "received_qty", "material_request", "purchase_order",
        )
        snapshot["items"] = [
            {field: row.get(field) for field in item_fields if row.get(field) not in (None, "")}
            for row in rows[:50]
            if isinstance(row, dict)
        ]
    return snapshot


def _submit_tool_for_doctype(doctype: str) -> str | None:
    if doctype in {"Material Request", "Request for Quotation", "Supplier Quotation", "Purchase Order", "Purchase Receipt"}:
        return "erpnext.buying.submit_document"
    if doctype in {"Stock Entry", "Stock Reconciliation"}:
        return "erpnext.stock.submit_document"
    if doctype in {"Purchase Invoice", "Sales Invoice", "Journal Entry", "Payment Entry"}:
        return "erpnext.accounting.submit_document"
    if doctype == "Asset":
        return "erpnext.assets.submit_document"
    return None


def _document_next_action_tools(observation: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for entity in observation.get("entities") or []:
        if not isinstance(entity, dict) or entity.get("kind") != "document":
            continue
        resolution = entity.get("resolution") or {}
        row = resolution.get("row") or {}
        for name in row.get("allowed_next_actions") or []:
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    return names[:5]


def _allowed_entity_values(session: RuntimeSessionState, observations: list[dict[str, Any]]) -> dict[str, set[str]]:
    allowed: dict[str, set[str]] = {kind: set() for kind in set(SENSITIVE_ENTITY_FIELDS.values())}
    if session.company:
        allowed["company"].add(session.company)
    if session.selected_project_code:
        allowed["project"].add(session.selected_project_code)
    if session.selected_warehouse_name:
        allowed["warehouse"].add(session.selected_warehouse_name)
    for names in session.documents.values():
        allowed["document"].update(names)
    for item in session.selected_entities.values():
        if isinstance(item, dict) and item.get("kind") in allowed and item.get("value"):
            allowed[item["kind"]].add(str(item["value"]))
        if isinstance(item, dict) and item.get("kind") == "document":
            _merge_document_snapshot_values(allowed, item.get("row"))
    for observation in observations:
        for item in _resolved_entity_values(observation).values():
            if item["kind"] in allowed:
                allowed[item["kind"]].add(str(item["value"]))
            if item.get("kind") == "document":
                _merge_document_snapshot_values(allowed, item.get("row"))
    return allowed


def _resolved_values_by_kind(session: RuntimeSessionState, observations: list[dict[str, Any]]) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    if session.company:
        values.setdefault("company", set()).add(session.company)
    if session.selected_warehouse_name:
        values.setdefault("warehouse", set()).add(session.selected_warehouse_name)
    for item in session.selected_entities.values():
        if isinstance(item, dict) and item.get("kind") and item.get("value"):
            values.setdefault(str(item["kind"]), set()).add(str(item["value"]))
        if isinstance(item, dict) and item.get("kind") == "document":
            _merge_document_snapshot_values(values, item.get("row"))
    for observation in observations:
        for item in _resolved_entity_values(observation).values():
            values.setdefault(str(item["kind"]), set()).add(str(item["value"]))
            if item.get("kind") == "document":
                _merge_document_snapshot_values(values, item.get("row"))
    return values


def _merge_document_snapshot_values(target: dict[str, set[str]], snapshot: Any) -> None:
    if not isinstance(snapshot, dict):
        return
    for field, kind in (("company", "company"), ("supplier", "supplier")):
        value = snapshot.get(field)
        if value:
            target.setdefault(kind, set()).add(str(value))
    for row in snapshot.get("items") or []:
        if not isinstance(row, dict):
            continue
        for field, kind in (("item_code", "item"), ("project", "project"), ("warehouse", "warehouse")):
            value = row.get(field)
            if value:
                target.setdefault(kind, set()).add(str(value))


def _inject_resolved_arguments(arguments: dict[str, Any], contract: ToolContract, session: RuntimeSessionState, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = _resolved_values_by_kind(session, observations)
    corrections: list[dict[str, Any]] = []
    for parameter in contract.parameters:
        if not parameter.resolver or parameter.name in {"items", "suppliers", "data"}:
            continue
        candidates = values.get(parameter.resolver) or set()
        if len(candidates) != 1:
            continue
        resolved = next(iter(candidates))
        if "[]." in parameter.name:
            collection_name, field_name = parameter.name.split("[].", 1)
            collection = arguments.get(collection_name)
            if not isinstance(collection, list):
                continue
            for index, row in enumerate(collection):
                if isinstance(row, dict) and row.get(field_name) in (None, ""):
                    row[field_name] = resolved
                    corrections.append({"field": f"{collection_name}[{index}].{field_name}", "value": resolved, "source": parameter.resolver})
        elif "." not in parameter.name and arguments.get(parameter.name) in (None, ""):
            arguments[parameter.name] = resolved
            corrections.append({"field": parameter.name, "value": resolved, "source": parameter.resolver})
    return corrections


def _inject_source_document_references(
    call: dict[str, Any],
    session: RuntimeSessionState,
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_config = {
        "erpnext.buying.create_request_for_quotation_draft": (
            "Material Request",
            "material_request",
            "material_request_item",
        ),
        "erpnext.buying.create_supplier_quotation_draft": (
            "Request for Quotation",
            "request_for_quotation",
            "request_for_quotation_item",
        ),
    }
    config = source_config.get(str(call.get("tool") or ""))
    arguments = call.get("arguments")
    if not config or not isinstance(arguments, dict) or not isinstance(arguments.get("items"), list):
        return []
    source_doctype, parent_field, row_field = config
    snapshots: list[dict[str, Any]] = []
    selected = list(session.selected_entities.values())
    for observation in observations:
        selected.extend(_resolved_entity_values(observation).values())
    for entity in reversed(selected):
        row = entity.get("row") if isinstance(entity, dict) and entity.get("kind") == "document" else None
        if isinstance(row, dict) and row.get("doctype") == source_doctype:
            snapshots.append(row)
    if not snapshots:
        return []

    corrections: list[dict[str, Any]] = []
    for index, item in enumerate(arguments["items"]):
        if not isinstance(item, dict) or item.get(parent_field) or item.get(row_field):
            continue
        item_code = str(item.get("item_code") or "")
        unique_matches: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
        for snapshot in snapshots:
            for source_row in snapshot.get("items") or []:
                if (
                    isinstance(source_row, dict)
                    and source_row.get("name")
                    and (not item_code or str(source_row.get("item_code") or "") == item_code)
                ):
                    key = (str(snapshot.get("name") or ""), str(source_row["name"]))
                    unique_matches[key] = (snapshot, source_row)
        matches = list(unique_matches.values())
        if len(matches) != 1:
            continue
        snapshot, source_row = matches[0]
        for field, value in (
            (parent_field, snapshot.get("name")),
            (row_field, source_row.get("name")),
            ("project", source_row.get("project")),
            ("warehouse", source_row.get("warehouse")),
        ):
            if value and item.get(field) in (None, ""):
                item[field] = value
                corrections.append({
                    "field": f"items[{index}].{field}",
                    "value": value,
                    "source": f"{source_doctype}.live_snapshot",
                })
    return corrections


def _inject_material_request_reference_prices(
    call: dict[str, Any],
    materials_by_code: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Use governed test reference prices; never accept a model-invented MR rate."""
    if call.get("tool") != "erpnext.buying.create_material_request_draft":
        return []
    arguments = call.get("arguments")
    if not isinstance(arguments, dict) or not isinstance(arguments.get("items"), list):
        return []
    corrections: list[dict[str, Any]] = []
    for index, row in enumerate(arguments["items"]):
        if not isinstance(row, dict):
            continue
        item_code = str(row.get("item_code") or row.get("selected_item_code") or "")
        source = materials_by_code.get(item_code) or {}
        try:
            rate = round(float(source.get("estimated_rate") or 0), 2)
        except (TypeError, ValueError):
            rate = 0
        if rate > 0:
            if row.get("rate") != rate:
                row["rate"] = rate
                corrections.append({
                    "field": f"items[{index}].rate",
                    "value": rate,
                    "source": "material_master.estimated_rate",
                    "price_basis": source.get("price_basis") or "测试参考价",
                })
        elif "rate" in row:
            row.pop("rate", None)
            corrections.append({
                "field": f"items[{index}].rate",
                "value": None,
                "source": "removed_unverified_model_rate",
            })
    return corrections


def _walk_arguments(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(child, (dict, list)):
                yield key, child
            yield from _walk_arguments(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_arguments(child)


def _observation_candidates(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for observation in observations:
        for entity in observation.get("entities") or []:
            resolution = entity.get("resolution") or {}
            if resolution.get("candidates"):
                result.append({"id": entity.get("id"), "kind": entity.get("kind"), "query": entity.get("query"), "candidates": resolution["candidates"]})
    return result


def _hydrate_presented_candidates(presented: list[Any], observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    available = _observation_candidates(observations)
    requested_codes = {
        str(candidate.get("item_code"))
        for group in presented
        for candidate in (group.get("candidates") if isinstance(group, dict) and isinstance(group.get("candidates"), list) else [group])
        if isinstance(candidate, dict) and candidate.get("item_code")
    }
    if not requested_codes:
        return available
    hydrated: list[dict[str, Any]] = []
    for group in available:
        rows = [row for row in group.get("candidates") or [] if str(row.get("item_code")) in requested_codes]
        if rows:
            hydrated.append({**group, "candidates": rows})
    return hydrated or available


def _validate_json_value(value: Any, schema: dict[str, Any], path: str) -> str | None:
    expected = schema.get("type")
    type_map = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
    if expected in type_map and (not isinstance(value, type_map[expected]) or expected in {"integer", "number"} and isinstance(value, bool)):
        return f"{path}必须是{expected}。"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}必须是以下值之一：{schema['enum']}。"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path}不得小于{schema['minimum']}。"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path}不得大于{schema['maximum']}。"
    if isinstance(value, str):
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{path}长度不得超过{schema['maxLength']}。"
        if schema.get("pattern") and not re.fullmatch(schema["pattern"], value):
            return f"{path}格式不符合要求。"
    if isinstance(value, dict):
        for required in schema.get("required") or []:
            if required not in value or value[required] in (None, ""):
                return f"{path}.{required}为必填字段。"
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                return f"{path}包含未知字段：{', '.join(unknown)}。"
        for key, child in value.items():
            if key in properties:
                error = _validate_json_value(child, properties[key], f"{path}.{key}")
                if error:
                    return error
    if isinstance(value, list) and schema.get("items"):
        for index, child in enumerate(value):
            error = _validate_json_value(child, schema["items"], f"{path}[{index}]")
            if error:
                return error
    return None


def _result_from_dict(payload: dict[str, Any]) -> DeepSeekTurnResult:
    data = dict(payload)
    for key in ("steps", "tool_calls", "tool_results", "questions", "candidates"):
        data[key] = tuple(data.get(key) or [])
    return DeepSeekTurnResult(**data)
