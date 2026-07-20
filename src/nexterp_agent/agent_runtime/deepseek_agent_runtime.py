from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from copy import deepcopy
import json
import re
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS
from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver
from nexterp_agent.master_data import MasterDataRelease

from .candidate_inventory import enrich_item_entity_results
from .action_models import validate_action
from .capability_registry import CapabilityRegistry
from .business_capabilities import (
    CapabilityCompilationError,
    FINANCE_GOALS,
    FinanceCapabilityCompiler,
    PROJECT_GOALS,
    ProjectCapabilityCompiler,
    PreparedBusinessAction,
    ProcurementCapabilityCompiler,
    ProcurementCapabilityGraph,
    STOCK_GOALS,
    StockCapabilityCompiler,
    canonical_tool_call_hash,
    verify_finance_result,
    verify_project_result,
    verify_procurement_result,
    verify_stock_result,
)
from .deepseek_material_request import DeepSeekSettings, call_deepseek_json
from .resolvers import EntityResolverRegistry, ResolutionResult
from .session import RuntimeSessionState, RuntimeSessionStore
from .tool_access import ToolExposure, make_tool_access_policy
from .tool_contracts import ToolContract, build_tool_contracts
from .tool_gateway import ToolGateway, ToolSession


MAX_AGENT_STEPS = 10
MAX_MODEL_RETRIES = 1
MAX_TOOL_REPAIRS = 2
PENDING_CONFIRMATION_TTL_MINUTES = 30
AGENT_ACTIONS = frozenset({
    "discover_tools", "discover_capabilities", "get_tool_contracts", "get_capability_guide",
    "resolve_entities", "propose_business_action", "execute_tool", "ask_user", "finish",
})
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
    try:
        validated = validate_action(payload)
    except ValidationError as exc:
        action = payload.get("action")
        if action not in AGENT_ACTIONS:
            raise ValueError(f"Unsupported DeepSeek action: {action}") from exc
        raise ValueError(_compact_validation_error(exc)) from exc
    payload.clear()
    payload.update(validated)
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
        self.capabilities = CapabilityRegistry()
        self.procurement_graph = ProcurementCapabilityGraph()
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
        conversation_id = str(selected_context.get("conversation_id") or "default")
        previous_conversation_id = str(session.business_state.get("conversation_id") or conversation_id)
        if previous_conversation_id != conversation_id:
            _clear_capability_draft(session)
            session.pending_action = None
        session.business_state["conversation_id"] = conversation_id
        if selected_context.get("project_code"):
            selected_project_code = str(selected_context["project_code"])
            if session.selected_project_code and session.selected_project_code != selected_project_code:
                _clear_capability_draft(session)
                session.pending_action = None
            session.selected_project_code = selected_project_code
        if selected_context.get("erpnext_project"):
            session.selected_entities["runtime_project"] = {
                "kind": "project",
                "value": str(selected_context["erpnext_project"]),
                "label": str(selected_context.get("project_code") or selected_context["erpnext_project"]),
                "row": {"project_code": selected_context.get("project_code")},
            }
        if selected_context.get("warehouse"):
            session.selected_warehouse_name = str(selected_context["warehouse"])
            session.selected_entities["runtime_warehouse"] = {
                "kind": "warehouse",
                "value": str(selected_context["warehouse"]),
                "label": str(selected_context["warehouse"]),
            }
        policy = make_tool_access_policy(profile)
        steps: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        confirmed_call: dict[str, Any] | None = None
        action_occurrences: dict[str, int] = {}
        today = today or date.today()

        if execute:
            pending = session.pending_action
            if not isinstance(pending, dict) or not isinstance(pending.get("tool_call"), dict):
                return self._save(session, user_text, DeepSeekTurnResult("failed", "没有等待确认的ToolCall。"), request_id)
            binding_error = _pending_binding_error(pending, session=session, user=user, profile=profile)
            if binding_error:
                session.pending_action = None
                return self._save(session, user_text, DeepSeekTurnResult("failed", binding_error), request_id)
            call = pending["tool_call"]
            pending_hash = str(pending.get("confirmation_hash") or "")
            if pending_hash and canonical_tool_call_hash(call) != pending_hash:
                session.pending_action = None
                return self._save(
                    session,
                    user_text,
                    DeepSeekTurnResult("failed", "待确认操作在确认前发生变化，已取消执行。请重新预览。"),
                    request_id,
                )
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
            if execution.ok:
                verification = self._verify_prepared_action(pending, payload, user=user)
                if verification:
                    payload["verification"] = verification
                    steps.append(_step("执行后回读", "verify_result", {"capability": pending.get("capability")}, verification))
                    self._remember_verified_business_action(session, pending, payload, verification)
                    if not verification.get("ok"):
                        result = DeepSeekTurnResult(
                            "completed",
                            f"{_successful_execution_message(payload)} 但执行后回读未完全通过，请人工检查该单据。",
                            tuple(steps),
                            tool_result=payload,
                            tool_results=tuple(tool_results),
                        )
                        return self._save(session, user_text, result, request_id)
                _clear_capability_draft(session, capability_id=str(pending.get("capability") or ""))
                result = DeepSeekTurnResult(
                    "completed",
                    _successful_execution_message(payload),
                    tuple(steps),
                    tool_result=payload,
                    tool_results=tuple(tool_results),
                )
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
            if _successful_read_requires_finish(observations, self.capabilities) and kind != "finish":
                observation = {
                    "type": "completion_required",
                    "error": "只读业务查询已经成功，本轮只能根据现有真实结果返回finish，禁止再次规划或查询。",
                }
                steps.append(_step("要求生成最终回复", "completion_required", arguments, observation))
                observations.append(observation)
                continue
            fingerprint = _agent_action_fingerprint(action)
            action_occurrences[fingerprint] = action_occurrences.get(fingerprint, 0) + 1
            if action_occurrences[fingerprint] == 2:
                observation = {
                    "type": "no_progress",
                    "action": kind,
                    "error": "相同动作已经执行过且没有产生新的业务进展，请改用已有结果继续或向用户追问。",
                }
                steps.append(_step("检测无进展", "no_progress", arguments, observation))
                observations.append(observation)
                continue
            if action_occurrences[fingerprint] > 2:
                result = DeepSeekTurnResult(
                    "failed",
                    f"Agent重复执行{kind}且没有取得新进展，已停止。",
                    tuple(steps),
                    tool_results=tuple(tool_results),
                )
                return self._save(session, user_text, result, request_id)

            if kind == "discover_tools":
                discovery_query = str(arguments.get("query") or user_text)
                cards = self.discovery.discover(discovery_query, policy=policy, modules=arguments.get("modules"), limit=int(arguments.get("limit") or 8))
                cards = [card for card in cards if card.get("name") not in self.capabilities.capability_tools]
                capability_cards = self.capabilities.discover(
                    discovery_query,
                    policy=policy,
                    modules=arguments.get("modules"),
                    limit=5,
                )
                auto_guide = _auto_load_capability_guide(
                    capability_cards,
                    registry=self.capabilities,
                    policy=policy,
                    session=session,
                )
                observation = {
                    "type": kind,
                    "tools": cards,
                    "capabilities": capability_cards,
                    "auto_loaded_guide": auto_guide,
                    "instruction": (
                        "唯一匹配的 Capability Guide 已自动加载，请直接解析实体并提交业务意图。"
                        if auto_guide
                        else "若存在匹配的 Capability，优先加载其 Guide；tools 仅用于尚未能力化的普通查询。"
                    ),
                }
                steps.append(_step("发现工具", kind, arguments, observation))
                observations.append(observation)
                continue
            if kind == "discover_capabilities":
                cards = self.capabilities.discover(
                    str(arguments.get("query") or user_text),
                    policy=policy,
                    modules=arguments.get("modules"),
                    limit=int(arguments.get("limit") or 5),
                )
                auto_guide = _auto_load_capability_guide(
                    cards,
                    registry=self.capabilities,
                    policy=policy,
                    session=session,
                )
                observation = {
                    "type": kind,
                    "capabilities": cards,
                    "auto_loaded_guide": auto_guide,
                    "instruction": (
                        "唯一匹配的 Capability Guide 已自动加载，请勿再次调用 get_capability_guide。"
                        if auto_guide
                        else "请从候选中选择能力并加载 Guide。"
                    ),
                }
                steps.append(_step("发现业务能力", kind, arguments, observation))
                observations.append(observation)
                continue
            if kind == "get_tool_contracts":
                tool_names = [
                    name
                    for name in arguments.get("tool_names") or []
                    if name not in self.capabilities.capability_tools
                ]
                contracts = self.discovery.full_contracts(tool_names, policy=policy)
                observation = {"type": kind, "contracts": contracts}
                steps.append(_step("读取契约", kind, arguments, observation))
                observations.append(observation)
                continue
            if kind == "get_capability_guide":
                guides = self.capabilities.guides(arguments.get("capability_ids") or [], policy=policy)
                observation = {"type": kind, "guides": guides}
                steps.append(_step("读取业务能力说明", kind, arguments, observation))
                observations.append(observation)
                if guides:
                    selected_capability_id = guides[0]["capability_id"]
                    if session.business_state.get("active_capability_id") != selected_capability_id:
                        _clear_capability_draft(session)
                    session.business_state["active_capability_id"] = selected_capability_id
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
                document_snapshots = _document_snapshots_from_observation(observation)
                if document_snapshots:
                    capability_observation = {
                        "type": "legal_business_capabilities",
                        "capabilities": self.procurement_graph.legal_actions(document_snapshots),
                    }
                    steps.append(_step("判断合法业务动作", "capability_graph", {}, capability_observation))
                    observations.append(capability_observation)
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
            if kind == "propose_business_action":
                try:
                    capability_id = str(arguments.get("capability_id") or "").strip()
                    raw_intent = arguments.get("business_intent") or {}
                    if not capability_id and self.planner is not None:
                        capability_id = self.capabilities.for_goal(str(raw_intent.get("goal") or "")).capability_id
                    loaded_ids = _loaded_capability_ids(observations)
                    active_id = str(session.business_state.get("active_capability_id") or "")
                    if capability_id not in loaded_ids and capability_id != active_id:
                        raise CapabilityCompilationError(
                            f"Capability {capability_id or '(missing)'} 尚未加载使用说明。",
                            questions=("请先发现并加载对应业务能力说明。",),
                        )
                    saved_draft = _capability_draft(session, capability_id)
                    merged_intent = _merge_capability_intent(saved_draft, raw_intent)
                    merged_intent = _normalize_runtime_entity_aliases(merged_intent, session)
                    definition, intent = self.capabilities.parse_intent(capability_id, merged_intent)
                    validated_intent = _canonical_intent_payload(intent)
                    session.business_state["capability_draft"] = {
                        "capability_id": capability_id,
                        "intent": validated_intent,
                    }
                    prepared = self._compile_business_action(
                        intent,
                        user=user,
                        session=session,
                        observations=observations,
                        today=today,
                    )
                    if prepared.capability != definition.capability_id:
                        raise CapabilityCompilationError("业务意图与所选 Capability 不一致。")
                    session.business_state["active_capability_id"] = capability_id
                except (ValueError, CapabilityCompilationError) as exc:
                    questions = tuple(getattr(exc, "questions", ()) or ())
                    error_message = _compact_validation_error(exc) if isinstance(exc, ValidationError) else str(exc)
                    observation = {
                        "type": "business_action_error",
                        "error": error_message,
                        "questions": list(questions),
                    }
                    steps.append(_step("业务预检", kind, arguments, observation))
                    observations.append(observation)
                    if sum(1 for item in observations if item.get("type") == "business_action_error") > MAX_TOOL_REPAIRS:
                        result = DeepSeekTurnResult(
                            "failed",
                            error_message,
                            tuple(steps),
                            tool_results=tuple(tool_results),
                        )
                        return self._save(session, user_text, result, request_id)
                    continue
                call = deepcopy(prepared.tool_call)
                contract = next((item for item in self.discovery.contracts if item.name == call.get("tool")), None)
                if contract and contract.name not in _loaded_contract_names(observations):
                    contract_observation = {"type": "get_tool_contracts", "contracts": [_full_contract(contract)]}
                    steps.append(_step(
                        "业务能力读取契约",
                        "get_tool_contracts",
                        {"tool_names": [contract.name]},
                        contract_observation,
                    ))
                    observations.append(contract_observation)
                validation_error = self._validate_proposed_call(
                    call,
                    user=user,
                    policy=policy,
                    session=session,
                    observations=observations,
                )
                if validation_error:
                    observation = {"type": "business_action_error", "error": validation_error, "tool_call": call}
                    steps.append(_step("业务预检", kind, prepared.to_dict(), observation))
                    observations.append(observation)
                    continue
                preflight_call = _business_preflight_call(prepared)
                if preflight_call:
                    preflight = self._execute(preflight_call, user=user, profile=profile)
                    preflight_payload = preflight.to_dict()
                    tool_results.append(preflight_payload)
                    steps.append(_step("实时业务预检", "execute_tool", preflight_call, preflight_payload))
                    preflight_data = preflight_payload.get("data") if isinstance(preflight_payload.get("data"), dict) else {}
                    shortages = preflight_data.get("shortages") if isinstance(preflight_data, dict) else []
                    if not preflight.ok or (shortages and call.get("arguments", {}).get("require_available_stock", True)):
                        observation = {
                            "type": "business_action_error",
                            "error": preflight.user_message or preflight.error or "实时库存预检未通过。",
                            "preflight": _safe_tool_result(preflight_payload),
                        }
                        steps.append(_step("库存预检未通过", "business_preflight", prepared.to_dict(), observation))
                        observations.append(observation)
                        continue
                    observations.append({
                        "type": "business_preflight",
                        "tool_call": preflight_call,
                        "result": _safe_tool_result(preflight_payload),
                    })
                prepared_payload = prepared.to_dict()
                intent_payload = _canonical_intent_payload(intent)
                steps.append(_step("业务能力编译", kind, {"intent": intent_payload}, prepared_payload))
                if prepared.write:
                    session.pending_action = _bind_pending_action({
                        "tool_call": call,
                        "steps": steps,
                        "observations": observations,
                        "user_text": user_text,
                        "capability": prepared.capability,
                        "prepared_action": prepared_payload,
                        "confirmation_hash": prepared.confirmation_hash,
                    }, session=session, user=user, profile=profile)
                    result = DeepSeekTurnResult(
                        "needs_confirmation",
                        prepared.summary,
                        tuple(steps),
                        pending_tool_call=call,
                        tool_call=call,
                        tool_calls=(call,),
                        tool_results=tuple(tool_results),
                        intent=intent_payload,
                    )
                    return self._save(session, user_text, result, request_id=None)
                previous = next(
                    (
                        observation.get("result")
                        for observation in reversed(observations)
                        if observation.get("type") == "tool_result"
                        and (
                            observation.get("business_goal") == prepared.goal
                            or _same_business_call(observation.get("tool_call"), call)
                        )
                        and isinstance(observation.get("result"), dict)
                        and observation["result"].get("ok")
                    ),
                    None,
                )
                if previous is not None:
                    steps.append(_step("跳过重复业务查询", kind, prepared_payload, {"reason": "same_read_only_business_call_already_succeeded"}))
                    _clear_capability_draft(session, capability_id=prepared.capability)
                    result = DeepSeekTurnResult(
                        "completed",
                        _successful_execution_message(previous),
                        tuple(steps),
                        tool_result=previous,
                        tool_results=tuple(tool_results),
                        intent=intent_payload,
                    )
                    return self._save(session, user_text, result, request_id)
                execution = self._execute(call, user=user, profile=profile)
                payload = execution.to_dict()
                tool_results.append(payload)
                steps.append(_step("ERPNext执行", "execute_tool", call, payload))
                self._remember_result(session, payload)
                if execution.ok:
                    _clear_capability_draft(session, capability_id=prepared.capability)
                observations.append({
                    "type": "tool_result",
                    "business_goal": prepared.goal,
                    "capability": prepared.capability,
                    "tool_call": call,
                    "result": _safe_tool_result(payload),
                })
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
                protected = self.capabilities.for_tool(str(call.get("tool") or "")) if isinstance(call, dict) else None
                if protected:
                    observation = {
                        "type": "capability_required",
                        "error": "该操作已有业务能力，必须加载 Capability Guide 后执行，禁止直接调用底层 ToolCall。",
                        "capability": protected.card(),
                    }
                    steps.append(_step("引导业务能力", "capability_required", call, observation))
                    observations.append(observation)
                    continue
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
                    corrections.extend(_inject_operational_dates(call, today))
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
                    session.pending_action = _bind_pending_action(
                        {"tool_call": call, "steps": steps, "observations": observations, "user_text": user_text},
                        session=session,
                        user=user,
                        profile=profile,
                    )
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

    def _compile_business_action(
        self,
        intent: BaseModel,
        *,
        user: str,
        session: RuntimeSessionState,
        observations: list[dict[str, Any]],
        today: date,
    ) -> PreparedBusinessAction:
        goal = str(intent.goal)
        if goal not in STOCK_GOALS:
            allowed_documents = _allowed_entity_values(session, observations).get("document") or set()
            for source in intent.source_documents:
                if source.name not in allowed_documents:
                    raise CapabilityCompilationError(
                        f"来源单据 {source.name} 尚未通过实体解析。",
                        questions=(f"请先核对来源单据 {source.name}。",),
                    )
            if goal in FINANCE_GOALS:
                compiler = FinanceCapabilityCompiler(self._business_document_loader(user))
            elif goal in PROJECT_GOALS:
                compiler = ProjectCapabilityCompiler(self._business_document_loader(user))
            else:
                compiler = ProcurementCapabilityCompiler(self._business_document_loader(user))
        else:
            compiler = StockCapabilityCompiler(self._business_document_loader(user))
        return compiler.compile(
            intent,
            runtime_context={
                "company": session.company,
                "project": _single_resolved_value("project", session, observations),
                "warehouse": _single_resolved_value("warehouse", session, observations),
            },
            today=today,
        )

    def _business_document_loader(self, user: str):
        if self.client_factory is None:
            raise CapabilityCompilationError("当前 Runtime 没有 ERPNext 客户端，无法读取业务单据。")
        client = self.client_factory(user)

        def load(doctype: str, name: str) -> dict[str, Any]:
            result = client.get_document(doctype, name)
            if not result.ok or not isinstance(result.data, dict):
                raise CapabilityCompilationError(result.user_message or result.error or f"无法读取 {doctype} {name}")
            snapshot = dict(result.data)
            snapshot.setdefault("doctype", doctype)
            snapshot.setdefault("name", name)
            return snapshot

        return load

    def _verify_prepared_action(self, pending: dict[str, Any], payload: dict[str, Any], *, user: str) -> dict[str, Any] | None:
        raw = pending.get("prepared_action")
        if not isinstance(raw, dict):
            return None
        prepared = PreparedBusinessAction(
            capability=str(raw.get("capability") or ""),
            goal=str(raw.get("goal") or ""),
            tool_call=deepcopy(raw.get("tool_call") or {}),
            summary=str(raw.get("summary") or ""),
            field_sources=dict(raw.get("field_sources") or {}),
            preflight_checks=tuple(raw.get("preflight_checks") or ()),
            confirmation_hash=str(raw.get("confirmation_hash") or ""),
            write=bool(raw.get("write", True)),
        )
        try:
            if prepared.goal in STOCK_GOALS:
                return verify_stock_result(prepared, payload, self._business_document_loader(user))
            if prepared.goal in FINANCE_GOALS:
                return verify_finance_result(prepared, payload, self._business_document_loader(user))
            if prepared.goal in PROJECT_GOALS:
                return verify_project_result(prepared, payload, self._business_document_loader(user))
            return verify_procurement_result(prepared, payload, self._business_document_loader(user))
        except CapabilityCompilationError as exc:
            return {"ok": False, "reason": str(exc), "checks": []}

    @staticmethod
    def _remember_verified_business_action(
        session: RuntimeSessionState,
        pending: dict[str, Any],
        payload: dict[str, Any],
        verification: dict[str, Any],
    ) -> None:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        history = session.business_state.setdefault("verified_actions", [])
        history.append({
            "capability": pending.get("capability"),
            "doctype": data.get("doctype"),
            "name": data.get("name"),
            "status": data.get("status"),
            "verified": bool(verification.get("ok")),
            "checks": list(verification.get("checks") or []),
        })
        session.business_state["verified_actions"] = history[-20:]

    def _messages(self, user_text: str, employee: dict[str, str], session: RuntimeSessionState, today: date, observations: list[dict[str, Any]], steps: list[dict[str, Any]]) -> list[dict[str, str]]:
        finish_only = _successful_read_requires_finish(observations, self.capabilities)
        system = (
            "你是懂业务的ERPNext员工助理，只返回协议中的单个JSON动作。"
            "负责理解目标、提取用户明确表达的信息、比较候选和友好追问；不要承担ERP事务编排。"
            "任何ERPNext主键必须来自resolve_entities或已确认上下文，禁止猜测。"
            "已确认上下文中的runtime_project是当前ERPNext项目主键；用户没有明确说另一个项目时直接使用，不要重复解析或追问。"
            "采购、库存、财务与项目业务先discover_capabilities；若结果已包含auto_loaded_guide，直接按Guide解析实体，"
            "否则再get_capability_guide；按Guide要求resolve_entities后，"
            "使用propose_business_action提交capability_id和业务意图。不得猜测Capability，也不得直接调用其底层写工具。"
            "未能力化的普通查询才使用discover_tools、get_tool_contracts和execute_tool。"
            "Runtime负责读取来源单据、限制合法下一步、编译ToolCall和等待一次用户确认。"
            "收到business_action_error时，若信息可从原话解析，应调用Resolver或修正业务意图；只有用户确实没说时才ask_user。"
            "单据启用ERPNext Workflow时，禁止使用任何submit_document工具；必须先执行erpnext.get_workflow_actions，"
            "再使用erpnext.apply_workflow执行当前账号真实可用的动作。反之，实时单据快照没有workflow_state且docstatus=0时，"
            "说明该单据未启用工作流：禁止调用get_workflow_actions或apply_workflow，必须发现并使用所属模块的submit_document工具。"
            "历史单号只是线索，后续操作必须重新resolve_entities(kind=document)读取实时状态。"
            "候选不唯一时ask_user并展示最相关候选；完成后只引用observation中的真实数字、状态和单号。"
            "summary仅用于审计；ask_user.message和finish.message要自然、简洁、可行动。不要展示隐藏思维过程。"
        )
        if finish_only:
            system += (
                "当前只读业务查询已经成功并返回真实结果。下一动作只能是finish：直接回答用户的问题，"
                "不得再次发现能力、解析实体、提交业务意图或执行工具。"
            )
        active_capability_id = str(session.business_state.get("active_capability_id") or "")
        active_capability_guide = None
        if active_capability_id:
            try:
                active_capability_guide = self.capabilities.get(active_capability_id).guide()
            except ValueError:
                active_capability_guide = None
        action_schemas = {
                "discover_capabilities": {"query": "描述所需业务能力，必填", "modules": ["stock | buying | accounting | projects"], "limit": "1-5"},
                "get_capability_guide": {"capability_ids": ["从discover_capabilities结果逐字复制，最多3个"]},
                "discover_tools": {"query": "描述所需业务能力，必填", "modules": ["generic | users | assets | stock | buying | accounting | projects"], "limit": "1-8"},
                "get_tool_contracts": {"tool_names": ["从discover_tools结果逐字复制的工具名，最多5个"]},
                "resolve_entities": {"entities": [{"id": "本轮唯一标识", "kind": "item | project | warehouse | supplier | company | employee | date | uom | document", "query": "用户原话或待核对主键", "specs": {}, "qty": "kind=item时可提供需求数量", "uom": "kind=item时可提供用户单位", "doctype": "kind=document时必填"}]},
                "propose_business_action": {"capability_id": "已加载Guide的Capability ID", "business_intent": "严格符合该Guide的intent_schema"},
                "execute_tool": {"tool_call": {"tool": "已读取契约的工具名", "arguments": {}}},
                "ask_user": {"message": "可直接展示给员工的自然回复", "questions": ["员工可直接回答的最少必要问题"], "candidates": ["从observation复制的相关候选，可省略并由Runtime补齐"]},
                "finish": {"message": "基于真实observation的最终答复"},
            }
        protocol = {
            "action_schema": {
                "action": "finish" if finish_only else "discover_capabilities | get_capability_guide | discover_tools | get_tool_contracts | resolve_entities | propose_business_action | execute_tool | ask_user | finish",
                "summary": "可审计的简短动作说明",
                "arguments": "必须符合对应action_schemas",
            },
            "action_schemas": {"finish": action_schemas["finish"]} if finish_only else action_schemas,
            "modules": MODULE_DESCRIPTIONS,
            "active_capability_guide": active_capability_guide,
            "active_capability_draft": _capability_draft(session, active_capability_id),
            "runtime_context": {
                "current_date": today.isoformat(), "employee": employee, "profile": session.profile,
                "company": session.company, "selected_project_code": session.selected_project_code,
                "selected_warehouse_name": session.selected_warehouse_name,
                "confirmed_entities": _compact_confirmed_entities(session.selected_entities),
                "documents": {key: values[-3:] for key, values in session.documents.items()},
                "verified_business_actions": (session.business_state.get("verified_actions") or [])[-5:],
                "recent_turns": _compact_recent_turns(session.turns),
            },
            "observations": [_compact_agent_observation(item) for item in observations[-8:]],
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
        source_error = _source_document_tool_error(call["tool"], session, observations)
        if source_error:
            return source_error
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
        return {
            "ROLE-GM": "manager",
            "ROLE-MAT-EQP-MGR": "procurement",
            "ROLE-OPS-MGR": "operations",
            "ROLE-PROJ-MGR": "project",
            "ROLE-TECH-LEAD": "technical",
            "ROLE-MATERIAL-CLERK": "project",
            "ROLE-FINANCE": "finance",
            "ROLE-SYSADMIN": "system_admin",
        }.get(employee["role_code"], "project")

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


def _single_resolved_value(kind: str, session: RuntimeSessionState, observations: list[dict[str, Any]]) -> str | None:
    values = _resolved_values_by_kind(session, observations).get(kind) or set()
    return next(iter(values)) if len(values) == 1 else None


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


def _document_snapshots_from_observation(observation: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for entity in observation.get("entities") or []:
        if not isinstance(entity, dict) or entity.get("kind") != "document":
            continue
        resolution = entity.get("resolution")
        if not isinstance(resolution, dict) or resolution.get("status") != "resolved":
            continue
        row = resolution.get("row")
        candidate = resolution.get("candidate")
        if not isinstance(row, dict) and not isinstance(candidate, dict):
            candidates = resolution.get("candidates") or []
            candidate = candidates[0] if len(candidates) == 1 and isinstance(candidates[0], dict) else None
        if not isinstance(row, dict) and isinstance(candidate, dict):
            row = candidate.get("row") or candidate
        if isinstance(row, dict):
            snapshots.append(dict(row))
    return snapshots


def _compact_confirmed_entities(entities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    compact: dict[str, dict[str, Any]] = {}
    for key, entity in list(entities.items())[-20:]:
        if not isinstance(entity, dict):
            continue
        compact[key] = {
            field: entity.get(field)
            for field in ("kind", "value", "label", "confidence", "reason", "row")
            if entity.get(field) not in (None, "", [], {})
        }
    return compact


def _compact_recent_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for turn in turns[-4:]:
        payload = turn.get("result") if isinstance(turn.get("result"), dict) else {}
        result.append({
            "user_text": str(turn.get("user_text") or "")[:300],
            "status": payload.get("status"),
            "message": str(payload.get("message") or "")[:400],
            "documents": [
                {"doctype": data.get("doctype"), "name": data.get("name")}
                for item in payload.get("tool_results") or []
                if isinstance(item, dict)
                for data in [item.get("data")]
                if isinstance(data, dict) and data.get("name")
            ][:5],
        })
    return result


def _compact_agent_observation(observation: dict[str, Any]) -> dict[str, Any]:
    kind = str(observation.get("type") or "")
    if kind == "resolve_entities":
        return {
            "type": kind,
            "entities": [
                _compact_entity_resolution(item)
                for item in observation.get("entities") or []
                if isinstance(item, dict)
            ],
            "inventory_query": observation.get("inventory_query"),
        }
    if kind == "get_tool_contracts":
        return {
            "type": kind,
            "contracts": [
                {
                    "name": item.get("name"),
                    "purpose": item.get("purpose"),
                    "confirm": item.get("confirm"),
                    "business_contract": (item.get("business_contract") or [])[:4],
                    "parameters": (item.get("parameters") or [])[:20],
                }
                for item in observation.get("contracts") or []
                if isinstance(item, dict)
            ],
        }
    if kind == "tool_result":
        return {
            "type": kind,
            "tool_call": observation.get("tool_call"),
            "result": _safe_tool_result(observation.get("result") or {}),
        }
    return observation


def _compact_entity_resolution(entity: dict[str, Any]) -> dict[str, Any]:
    resolution = entity.get("resolution") if isinstance(entity.get("resolution"), dict) else {}
    compact_resolution = {
        field: resolution.get(field)
        for field in ("status", "value", "label", "confidence", "reason", "question", "decision_reason")
        if resolution.get(field) not in (None, "", [], {})
    }
    row = resolution.get("row")
    if isinstance(row, dict):
        compact_resolution["row"] = row
    resolved = resolution.get("resolved")
    if isinstance(resolved, dict):
        compact_resolution["resolved"] = _compact_material_candidate(resolved)
    candidates = resolution.get("candidates") or []
    compact_resolution["candidates"] = [
        _compact_material_candidate(candidate)
        for candidate in candidates[:5]
        if isinstance(candidate, dict)
    ]
    return {
        "id": entity.get("id"),
        "kind": entity.get("kind"),
        "query": entity.get("query"),
        "requested_qty": entity.get("requested_qty"),
        "requested_uom": entity.get("requested_uom"),
        "resolution": compact_resolution,
    }


def _compact_material_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        field: candidate.get(field)
        for field in (
            "value", "label", "item_code", "item_name", "sku_name", "required_specs",
            "stock_uom", "score", "confidence", "match_reason", "inventory_summary",
        )
        if candidate.get(field) not in (None, "", [], {})
    }


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


def _bind_pending_action(
    pending: dict[str, Any],
    *,
    session: RuntimeSessionState,
    user: str,
    profile: str,
) -> dict[str, Any]:
    payload = deepcopy(pending)
    call = payload.get("tool_call")
    if isinstance(call, dict):
        payload.setdefault("confirmation_hash", canonical_tool_call_hash(call))
    now = datetime.now().astimezone()
    runtime_project = session.selected_entities.get("runtime_project") or {}
    payload["binding"] = {
        "user": user,
        "profile": profile,
        "session_id": session.session_id,
        "conversation_id": str(session.business_state.get("conversation_id") or "default"),
        "project_code": session.selected_project_code,
        "erpnext_project": runtime_project.get("value") if isinstance(runtime_project, dict) else None,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=PENDING_CONFIRMATION_TTL_MINUTES)).isoformat(),
    }
    return payload


def _pending_binding_error(
    pending: dict[str, Any],
    *,
    session: RuntimeSessionState,
    user: str,
    profile: str,
) -> str | None:
    binding = pending.get("binding")
    if not isinstance(binding, dict):
        return "该待确认操作来自旧会话，已失效。请重新预览。"
    expected = {
        "user": user,
        "profile": profile,
        "session_id": session.session_id,
        "conversation_id": str(session.business_state.get("conversation_id") or "default"),
        "project_code": session.selected_project_code,
    }
    runtime_project = session.selected_entities.get("runtime_project") or {}
    expected["erpnext_project"] = runtime_project.get("value") if isinstance(runtime_project, dict) else None
    for field, value in expected.items():
        if binding.get(field) != value:
            return "待确认操作的员工、项目或会话已经变化，已取消执行。请重新预览。"
    try:
        expires_at = datetime.fromisoformat(str(binding.get("expires_at") or ""))
    except ValueError:
        return "待确认操作缺少有效期限，已取消执行。请重新预览。"
    now = datetime.now().astimezone()
    if expires_at.tzinfo is None:
        expires_at = expires_at.astimezone()
    if expires_at <= now:
        return "待确认操作已超过30分钟有效期，已取消执行。请重新预览。"
    return None


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


def _source_document_tool_error(tool: str, session: RuntimeSessionState, observations: list[dict[str, Any]]) -> str | None:
    doctypes: set[str] = set()
    selected = list(session.selected_entities.values())
    for observation in observations:
        selected.extend(_resolved_entity_values(observation).values())
    for entity in selected:
        row = entity.get("row") if isinstance(entity, dict) and entity.get("kind") == "document" else None
        if isinstance(row, dict) and row.get("doctype"):
            doctypes.add(str(row["doctype"]))
    preferred = {
        ("erpnext.buying.create_purchase_order_draft", "Supplier Quotation"):
            "erpnext.buying.create_purchase_order_from_supplier_quotation_draft",
        ("erpnext.buying.create_purchase_order_draft", "Material Request"):
            "erpnext.buying.create_purchase_order_from_material_request_draft",
        ("erpnext.buying.create_purchase_receipt_draft", "Purchase Order"):
            "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
        ("erpnext.accounting.create_purchase_invoice_draft", "Purchase Receipt"):
            "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
    }
    for (generic_tool, source_doctype), source_tool in preferred.items():
        if tool == generic_tool and source_doctype in doctypes:
            return f"已解析到{source_doctype}来源单据，必须使用{source_tool}保留来源引用。"
    return None


def _inject_resolved_arguments(arguments: dict[str, Any], contract: ToolContract, session: RuntimeSessionState, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = _resolved_values_by_kind(session, observations)
    corrections: list[dict[str, Any]] = []
    for parameter in contract.parameters:
        if not parameter.resolver or parameter.name in {"items", "selected_items", "suppliers", "data"}:
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
                if isinstance(row, dict) and row.get(field_name) != resolved:
                    row[field_name] = resolved
                    corrections.append({"field": f"{collection_name}[{index}].{field_name}", "value": resolved, "source": parameter.resolver})
        elif "." not in parameter.name and arguments.get(parameter.name) != resolved:
            arguments[parameter.name] = resolved
            corrections.append({"field": parameter.name, "value": resolved, "source": parameter.resolver})
    return corrections


def _inject_operational_dates(call: dict[str, Any], today: date) -> list[dict[str, Any]]:
    """Keep system business dates separate from user-supplied need/validity dates."""
    arguments = call.get("arguments")
    tool = str(call.get("tool") or "")
    if not tool.startswith(("erpnext.buying.create_", "erpnext.accounting.create_")) or not isinstance(arguments, dict):
        return []
    corrections: list[dict[str, Any]] = []
    current_date = today.isoformat()
    for field in ("transaction_date", "posting_date"):
        if field in arguments and arguments.get(field) != current_date:
            arguments[field] = current_date
            corrections.append({"field": field, "value": current_date, "source": "runtime.today"})
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


def _business_preflight_call(prepared: PreparedBusinessAction) -> dict[str, Any] | None:
    """Return a read-only live-state check that must pass before showing confirmation."""
    arguments = prepared.tool_call.get("arguments") or {}
    if prepared.goal == "create_stock_transfer":
        return {
            "tool": "erpnext.stock.get_transfer_context",
            "arguments": {
                "source_warehouse": arguments.get("source_warehouse"),
                "target_warehouse": arguments.get("target_warehouse"),
                "items": deepcopy(arguments.get("items") or []),
            },
        }
    if prepared.goal == "create_project_material_issue":
        return {
            "tool": "erpnext.projects.get_material_issue_context",
            "arguments": {
                "project": arguments.get("project"),
                "source_warehouse": arguments.get("source_warehouse"),
                "items": deepcopy(arguments.get("items") or []),
            },
        }
    return None


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


def _loaded_capability_ids(observations: list[dict[str, Any]]) -> set[str]:
    loaded = {
        str(guide.get("capability_id"))
        for observation in observations
        if observation.get("type") == "get_capability_guide"
        for guide in observation.get("guides") or []
        if isinstance(guide, dict) and guide.get("capability_id")
    }
    loaded.update(
        str(guide.get("capability_id"))
        for observation in observations
        for guide in [observation.get("auto_loaded_guide")]
        if isinstance(guide, dict) and guide.get("capability_id")
    )
    return loaded


def _successful_read_requires_finish(
    observations: list[dict[str, Any]],
    registry: CapabilityRegistry,
) -> bool:
    """Return true once the current read capability has produced a real result."""
    for observation in reversed(observations):
        if observation.get("type") != "tool_result":
            continue
        capability_id = str(observation.get("capability") or "")
        result = observation.get("result")
        if not capability_id or not isinstance(result, dict) or not result.get("ok"):
            return False
        try:
            return not registry.get(capability_id).write
        except ValueError:
            return False
    return False


def _auto_load_capability_guide(
    cards: list[dict[str, Any]],
    *,
    registry: CapabilityRegistry,
    policy: Any,
    session: RuntimeSessionState,
) -> dict[str, Any] | None:
    if not cards:
        return None
    first_score = int(cards[0].get("match_score") or 0)
    second_score = int(cards[1].get("match_score") or 0) if len(cards) > 1 else 0
    if first_score < 2 or (second_score and first_score < second_score * 2):
        return None
    capability_id = str(cards[0].get("capability_id") or "")
    guides = registry.guides([capability_id], policy=policy)
    if not guides:
        return None
    if session.business_state.get("active_capability_id") != capability_id:
        _clear_capability_draft(session)
    session.business_state["active_capability_id"] = capability_id
    return guides[0]


def _agent_action_fingerprint(action: dict[str, Any]) -> str:
    payload = {
        "action": action.get("action"),
        "arguments": action.get("arguments") or {},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _capability_draft(session: RuntimeSessionState, capability_id: str) -> dict[str, Any]:
    draft = session.business_state.get("capability_draft")
    if not isinstance(draft, dict) or str(draft.get("capability_id") or "") != capability_id:
        return {}
    intent = draft.get("intent")
    return deepcopy(intent) if isinstance(intent, dict) else {}


def _canonical_intent_payload(intent: BaseModel) -> dict[str, Any]:
    payload = intent.model_dump(exclude_none=True, exclude_defaults=True)
    payload["goal"] = str(intent.goal)
    return payload


def _clear_capability_draft(session: RuntimeSessionState, capability_id: str = "") -> None:
    draft = session.business_state.get("capability_draft")
    if capability_id and isinstance(draft, dict) and str(draft.get("capability_id") or "") != capability_id:
        return
    session.business_state.pop("capability_draft", None)
    active_id = str(session.business_state.get("active_capability_id") or "")
    if not capability_id or active_id == capability_id:
        session.business_state.pop("active_capability_id", None)


def _merge_capability_intent(previous: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(previous) if isinstance(previous, dict) else {}
    for key, value in (update or {}).items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_capability_intent(current, value)
        elif isinstance(current, list) and isinstance(value, list) and all(isinstance(item, dict) for item in current + value):
            rows = deepcopy(current)
            for index, item in enumerate(value):
                if index < len(rows):
                    rows[index] = _merge_capability_intent(rows[index], item)
                else:
                    rows.append(deepcopy(item))
            merged[key] = rows
        else:
            merged[key] = deepcopy(value)
    return merged


def _normalize_runtime_entity_aliases(payload: dict[str, Any], session: RuntimeSessionState) -> dict[str, Any]:
    """Translate the selected UI project alias into the live ERPNext Link value."""
    normalized = deepcopy(payload)
    runtime_project = session.selected_entities.get("runtime_project")
    if not isinstance(runtime_project, dict) or not runtime_project.get("value"):
        return normalized
    value = str(runtime_project["value"])
    row = runtime_project.get("row") if isinstance(runtime_project.get("row"), dict) else {}
    aliases = {
        str(candidate).strip()
        for candidate in (
            value,
            runtime_project.get("label"),
            row.get("project_code"),
            session.selected_project_code,
        )
        if str(candidate or "").strip()
    }

    def normalize_project_field(container: dict[str, Any]) -> None:
        project = str(container.get("project") or "").strip()
        if project in aliases:
            container["project"] = value

    normalize_project_field(normalized)
    for item in normalized.get("items") or []:
        if isinstance(item, dict):
            normalize_project_field(item)
    return normalized


def _compact_validation_error(error: ValidationError) -> str:
    details = []
    for item in error.errors(include_url=False)[:5]:
        location = ".".join(str(part) for part in item.get("loc") or ()) or "action"
        details.append(f"{location}: {item.get('msg')}")
    return "；".join(details) or "DeepSeek动作不符合协议"


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
