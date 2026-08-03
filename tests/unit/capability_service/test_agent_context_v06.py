from __future__ import annotations

from typing import Any

from nexterp_agent.capability_service.catalog import ExternalIdentity
from nexterp_agent.capability_service.context import AgentContextBuilder
from nexterp_agent.capability_service.models import CapabilitySearchRequest, PrepareOperationRequest, RequestIdentity
from nexterp_agent.capability_service.service import CapabilityManualService
from nexterp_agent.erpnext.schemas import ToolResult
from nexterp_agent.master_data import MasterDataRelease
from nexterp_agent.capability_service.role_catalog import ROLE_CAPABILITY_LINKS


def identity_for(user: str, project: str, profile: str = "project_agent") -> ExternalIdentity:
    return ExternalIdentity(
        external_subject=f"workbench:{user}", agent_id="main", employee_user=user,
        profile_name=profile, default_project=project, allowed_projects=(project,),
    )


def test_all_nine_employees_build_trusted_context_for_eight_roles() -> None:
    release = MasterDataRelease()
    builder = AgentContextBuilder()
    roles = set()
    employees = list(release.employees.values())
    assert len(employees) == 9
    for employee in employees:
        project = "PRJ-HL-13" if employee["employee_code"] == "EMP-PANFENG" else (employee.get("default_project_code") or "PRJ-HL-13")
        context = builder.build(identity_for(employee["user_email"], project), {
            "project_code": project, "current_goal": "查看今天的工作", "intent_mode": "read",
        })
        assert context.identity.employee_name == employee["employee_name"]
        assert context.workplace.project_code == project
        assert context.provenance["permissions"].trust == "authoritative"
        roles.add(context.identity.role_code)
    assert roles == {
        "ROLE-GM", "ROLE-MAT-EQP-MGR", "ROLE-MATERIAL-CLERK", "ROLE-PROJ-MGR",
        "ROLE-TECH-LEAD", "ROLE-OPS-MGR", "ROLE-FINANCE", "ROLE-SYSADMIN",
    }
    assert set(ROLE_CAPABILITY_LINKS) == roles
    assert all("cap.document_lookup" in links for links in ROLE_CAPABILITY_LINKS.values())


def test_same_employee_uses_project_assignment_role_at_base() -> None:
    context = AgentContextBuilder().build(
        identity_for("pan.feng@stec-up.local", "PRJ-WCL-BASE"),
        {"project_code": "PRJ-WCL-BASE", "intent_mode": "read"},
    )
    assert context.identity.role_code == "ROLE-PROJ-MGR"
    assert context.identity.project_position == "项目经理"
    assert context.workplace.warehouse_code == "WH-WCL-BASE"


class ReadRepository:
    def __init__(self) -> None:
        self.identity = identity_for("mao.xiaoquan@stec-up.local", "PRJ-HL-13", "material_clerk_agent")
        self.misses = 0

    def resolve_identity(self, _subject: str, _agent_id: str = "") -> ExternalIdentity:
        return self.identity

    def session_context(self, _identity: ExternalIdentity, _session_key: str) -> dict[str, Any]:
        return {"project_code": "PRJ-HL-13", "intent_mode": "read", "employee_user": self.identity.employee_user}

    def search_nodes(self, _query: str, *, module: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        return [
            {"node_id": "op.material.search", "node_type": "operation", "module": "stock", "label": "查询标准物料与库存",
             "summary": "查询", "operation_mode": "read", "is_write": False},
            {"node_id": "op.material_request.create", "node_type": "operation", "module": "buying", "label": "创建材料申请",
             "summary": "创建", "operation_mode": "write", "is_write": True},
        ][:limit]

    def record_search_result(self, _identity: ExternalIdentity, _session_key: str, *, found: bool) -> int:
        self.misses = 0 if found else self.misses + 1
        return self.misses

    def current_revision(self) -> str:
        return "v0.6-test"


class ReadReferenceData:
    def options(self, entity: str, *, query: str = "", project: str = "", item_code: str = "") -> list[dict[str, Any]]:
        if entity == "item":
            return [{"value": "TOOL-DRILL-14", "label": "麻花钻头 14mm", "meta": "直径：14mm",
                     "stock_uom": "支", "score": 99, "match_reason": "名称和直径匹配"}]
        if entity == "warehouse":
            return [{"value": "合流1.3标仓库 - SD", "label": "合流1.3标仓库"},
                    {"value": "蕰川路基地仓库 - SD", "label": "蕰川路基地仓库"}]
        return []


class ReadClient:
    def get_logged_user(self) -> ToolResult:
        return ToolResult(ok=True, data="mao.xiaoquan@stec-up.local")

    def search_documents(self, doctype: str, **_kwargs: Any) -> ToolResult:
        assert doctype == "Bin"
        return ToolResult(ok=True, data=[
            {"item_code": "TOOL-DRILL-14", "warehouse": "合流1.3标仓库 - SD", "actual_qty": 6,
             "reserved_qty": 1, "projected_qty": 5},
            {"item_code": "TOOL-DRILL-14", "warehouse": "蕰川路基地仓库 - SD", "actual_qty": 20,
             "reserved_qty": 0, "projected_qty": 20},
        ])


def test_read_mode_hides_write_capability_and_material_query_enriches_inventory() -> None:
    repository = ReadRepository()
    service = CapabilityManualService(
        repository, reference_data=ReadReferenceData(), client_factory=lambda _user: ReadClient(),
    )
    request_identity = RequestIdentity(external_subject="owner", agent_id="main", session_key="session-v06")
    discovery = service.search(CapabilitySearchRequest(query="物料表里有没有14的钻头"), request_identity)
    result = service.prepare(PrepareOperationRequest(
        operation_id="op.material.search", request_id="read-1", query="14的钻头", limit=10,
    ), request_identity)

    assert [card["node_id"] for card in discovery["cards"]] == ["op.material.search"]
    assert result["status"] == "completed"
    assert result["operation_mode"] == "read"
    assert result["candidates"][0]["item_code"] == "TOOL-DRILL-14"
    assert result["candidates"][0]["total_actual_qty"] == 26
    assert len(result["candidates"][0]["inventory"]) == 2


def test_second_capability_miss_stops_instead_of_selecting_a_similar_write() -> None:
    repository = ReadRepository()
    repository.search_nodes = lambda *_args, **_kwargs: []  # type: ignore[method-assign]
    service = CapabilityManualService(repository, reference_data=ReadReferenceData(), client_factory=lambda _user: ReadClient())
    identity = RequestIdentity(external_subject="owner", agent_id="main", session_key="session-v06")

    first = service.search(CapabilitySearchRequest(query="未知查询"), identity)
    second = service.search(CapabilitySearchRequest(query="扩大后的未知查询"), identity)

    assert first["status"] == "not_found"
    assert second["status"] == "unsupported"
    assert second["cards"] == []
