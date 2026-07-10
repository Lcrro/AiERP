from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Any, Callable

from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver
from nexterp_agent.master_data import MasterDataRelease

from .deepseek_material_request import extract_material_request_intent_with_deepseek
from .material_request_orchestrator import compose_material_request_tool_call
from .resolvers import EntityResolverRegistry, ResolutionResult
from .session import RuntimeSessionState, RuntimeSessionStore
from .tool_access import make_tool_access_policy
from .tool_gateway import ToolGateway, ToolSession


IntentExtractor = Callable[..., dict[str, Any]]
ClientFactory = Callable[[str], ERPNextClient]


@dataclass(frozen=True)
class RuntimeTurnResult:
    status: str
    message: str
    intent: dict[str, Any]
    resolutions: dict[str, Any]
    tool_call: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    questions: tuple[str, ...] = ()
    candidates: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CivilAgentRuntime:
    def __init__(
        self,
        *,
        release: MasterDataRelease | None = None,
        intent_extractor: IntentExtractor = extract_material_request_intent_with_deepseek,
        client_factory: ClientFactory | None = None,
        session_store: RuntimeSessionStore | None = None,
    ) -> None:
        self.release = release or MasterDataRelease()
        self.intent_extractor = intent_extractor
        self.client_factory = client_factory
        self.session_store = session_store or RuntimeSessionStore()
        self.entity_resolvers = EntityResolverRegistry(self.release)
        self.material_resolver = ReleaseMaterialResolver(self.release.material_release_path)

    def run_once(self, user_text: str, *, user: str, execute: bool = False, today: date | None = None) -> RuntimeTurnResult:
        employee = self._employee_for_user(user)
        profile = self._profile_for_employee(employee)
        session = self.session_store.load(user, profile=profile)
        today = today or date.today()
        extraction_context = {"current_date": today.isoformat(), "employee": employee["employee_name"]}
        intent = self.intent_extractor(user_text, context=extraction_context)
        if intent.get("intent") != "create_material_request":
            result = RuntimeTurnResult("unsupported_intent", "目前这条 CLI 主线先支持材料申请。", intent, {})
            self._save_turn(session, user_text, result)
            return result

        project_query = intent.get("project_text") or session.selected_project_code or employee.get("default_project_code")
        warehouse_query = intent.get("warehouse_text") or session.selected_warehouse_name or employee.get("default_warehouse_code")
        # Relative language is always resolved deterministically by Runtime;
        # model-produced ISO dates must not override words such as "明天".
        date_query = intent.get("schedule_text") or intent.get("schedule_date")
        company = self.entity_resolvers.resolve_company()
        project = self.entity_resolvers.resolve_project(project_query)
        warehouse = self.entity_resolvers.resolve_warehouse(warehouse_query)
        schedule = self.entity_resolvers.resolve_date(date_query, current_date=today)
        project = self._resolve_live_project_name(user, project)
        resolutions = {
            "company": company.to_dict(),
            "project": project.to_dict(),
            "warehouse": warehouse.to_dict(),
            "schedule_date": schedule.to_dict(),
        }

        questions = [
            resolution.question
            for resolution in (company, project, warehouse, schedule)
            if resolution.status != "resolved" and resolution.question
        ]
        if questions:
            result = RuntimeTurnResult("needs_clarification", "还需要补充一些信息。", intent, resolutions, questions=tuple(questions))
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result)
            return result

        normalized_intent = dict(intent)
        normalized_intent["company"] = company.value
        normalized_intent["schedule_date"] = schedule.value
        context = {
            "company": company.value,
            "default_schedule_date": schedule.value,
            "project_candidates": [{"name": project.value, "label": project.label}],
            "warehouse_candidates": [{"name": warehouse.value, "label": warehouse.label}],
        }
        composition = compose_material_request_tool_call(
            normalized_intent,
            context=context,
            resolver=self.material_resolver,
        )
        resolutions["materials"] = {
            "resolved_items": composition.get("resolved_items", []),
            "pending_resolutions": composition.get("pending_resolutions", []),
            "item_creation_requests": composition.get("item_creation_requests", []),
        }

        if composition["status"] != "ready":
            candidates = tuple(composition.get("pending_resolutions", []))
            result = RuntimeTurnResult(
                composition["status"],
                "物料还不能唯一确定。" if candidates else "材料申请信息还不完整。",
                intent,
                resolutions,
                questions=tuple(composition.get("questions", [])),
                candidates=candidates,
            )
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result)
            return result

        tool_call = composition["tool_call"]
        session.company = company.value
        session.selected_project_code = project.value
        session.selected_warehouse_name = warehouse.value
        if not execute:
            result = RuntimeTurnResult(
                "needs_confirmation",
                "材料申请草稿已经编排完成，确认后可以写入 ERPNext。",
                intent,
                resolutions,
                tool_call=tool_call,
            )
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result)
            return result

        if self.client_factory is None:
            raise RuntimeError("ERPNext client factory is required for execute mode")
        client = self.client_factory(user)
        policy = make_tool_access_policy(profile, extra_allowed_tools={tool_call["tool"]})
        gateway = ToolGateway(
            ERPNextAdapter(client),
            ToolSession(user=user, policy=policy, verify_erpnext_identity=True),
        )
        execution = gateway.execute(tool_call, origin="agent")
        tool_result = execution.to_dict()
        if execution.ok:
            document_name = _extract_document_name(execution.data)
            if document_name:
                session.remember_document("Material Request", document_name)
            message = f"材料申请草稿已创建：{document_name or 'ERPNext 已返回成功结果'}。"
            status = "completed"
            session.pending = None
        else:
            message = execution.user_message or "ERPNext 执行失败。"
            status = "failed"
        result = RuntimeTurnResult(status, message, intent, resolutions, tool_call, tool_result)
        self._save_turn(session, user_text, result)
        return result

    def _employee_for_user(self, user: str) -> dict[str, str]:
        for row in self.release.employees.values():
            if row["user_email"] == user:
                return row
        raise KeyError(f"Employee not found for user: {user}")

    def _profile_for_employee(self, employee: dict[str, str]) -> str:
        mapping = {
            "ROLE-GM": "manager",
            "ROLE-MAT-EQP-MGR": "procurement",
            "ROLE-OPS-MGR": "manager",
            "ROLE-PROJ-MGR": "project",
            "ROLE-TECH-LEAD": "project",
            "ROLE-MATERIAL-CLERK": "project",
            "ROLE-SYSADMIN": "system_admin",
        }
        return mapping.get(employee["role_code"], "project")

    def _resolve_live_project_name(self, user: str, resolution: ResolutionResult) -> ResolutionResult:
        if resolution.status != "resolved" or not resolution.value or self.client_factory is None:
            return resolution
        project = self.release.projects.get(resolution.value)
        if not project:
            return resolution
        client = self.client_factory(user)
        result = client.search_documents(
            "Project",
            filters={"project_name": project["project_name"]},
            fields=["name", "project_name"],
            limit=2,
        )
        if not result.ok or not isinstance(result.data, list):
            return replace(
                resolution,
                status="needs_clarification",
                value=None,
                question="无法从 ERPNext 读取该项目，请检查员工项目权限。",
                reason=result.error or "ERPNext project lookup failed",
            )
        if len(result.data) != 1:
            return replace(
                resolution,
                status="needs_selection",
                value=None,
                question="ERPNext 中没有找到唯一项目，请先核对项目主数据。",
                reason=f"ERPNext project matches={len(result.data)}",
            )
        actual_name = result.data[0].get("name")
        return replace(resolution, value=actual_name, reason=f"{resolution.reason}；ERPNext项目主键已核对")

    def _save_turn(self, session: RuntimeSessionState, user_text: str, result: RuntimeTurnResult) -> None:
        session.add_turn({"user_text": user_text, "result": result.to_dict()})
        self.session_store.save(session)


def _extract_document_name(data: Any) -> str | None:
    if isinstance(data, dict):
        if isinstance(data.get("name"), str):
            return data["name"]
        document = data.get("document")
        if isinstance(document, dict) and isinstance(document.get("name"), str):
            return document["name"]
    return None
