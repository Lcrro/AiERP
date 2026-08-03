from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from nexterp_agent.capability_service.catalog import ExternalIdentity
from nexterp_agent.capability_service.models import (
    CapabilitySearchRequest,
    PrepareOperationRequest,
    RequestIdentity,
)
from nexterp_agent.capability_service.procurement_catalog import OPERATION_BY_ID
from nexterp_agent.capability_service.service import CapabilityManualService
from nexterp_agent.erpnext.schemas import ToolResult


REQUEST_IDENTITY = RequestIdentity(
    external_subject="procurement-owner",
    agent_id="nexterp",
    session_key="procurement-session",
)
PROCUREMENT_IDENTITY = ExternalIdentity(
    external_subject="procurement-owner",
    agent_id="nexterp",
    employee_user="buyer@example.com",
    profile_name="material_equipment_agent",
    default_project="PRJ-HL-13",
    allowed_projects=("PRJ-HL-13",),
)


def operation_bundle(operation_id: str) -> dict[str, Any]:
    seed = OPERATION_BY_ID[operation_id]
    return {
        "operation": {
            "operation_id": seed.operation_id,
            "label": seed.operation_label,
            "tool_name": seed.tool_name,
            "compiler_key": seed.compiler_key,
            "requires_confirmation": True,
        },
        "slots": list(seed.slots),
        "rules": [
            {"rule_id": rule_id, "label": label, "message": message}
            for rule_id, label, message in seed.rules
        ],
    }


class FakeRepository:
    def __init__(self, identity: ExternalIdentity = PROCUREMENT_IDENTITY) -> None:
        self.identity = identity
        self.pending: dict[str, dict[str, Any]] = {}

    def resolve_identity(self, external_subject: str, agent_id: str = "") -> ExternalIdentity:
        if (external_subject, agent_id) != (self.identity.external_subject, self.identity.agent_id):
            raise PermissionError("not bound")
        return self.identity

    def current_revision(self) -> str:
        return "procurement-manual-test"

    def search_nodes(self, query: str, *, module: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        return [
            {
                "node_id": seed.operation_id,
                "node_type": "operation",
                "module": "buying",
                "label": seed.operation_label,
                "summary": seed.operation_summary,
                "is_write": True,
                "score": 100,
            }
            for seed in OPERATION_BY_ID.values()
        ][:limit]

    def load_guides(self, node_ids: list[str]) -> list[dict[str, Any]]:
        return []

    def operation_bundle(self, operation_id: str) -> dict[str, Any]:
        return operation_bundle(operation_id)

    def create_pending(self, **kwargs: Any) -> dict[str, Any]:
        row = {
            "pending_id": f"pending-{len(self.pending) + 1}",
            "operation_id": kwargs["operation_id"],
            "employee_user": kwargs["identity"].employee_user,
            "project_code": kwargs["project_code"],
            "external_subject": kwargs["identity"].external_subject,
            "agent_id": kwargs["identity"].agent_id,
            "session_key": kwargs["session_key"],
            "request_id": kwargs["request_id"],
            "catalog_revision": self.current_revision(),
            "tool_call": kwargs["tool_call"],
            "tool_call_hash": "frozen",
            "summary": kwargs["summary"],
            "status": "pending",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "result": None,
        }
        self.pending[row["pending_id"]] = row
        return row


class FakeReferenceData:
    def options(self, entity: str, *, query: str = "", project: str = "", item_code: str = "") -> list[dict[str, Any]]:
        if entity == "project":
            if not query or query in {"PROJ-0010", "PRJ-HL-13", "合流1.3标"}:
                return [{"value": "PROJ-0010", "source_code": "PRJ-HL-13", "label": "合流1.3标"}]
            return []
        if entity == "warehouse":
            return [{"value": "合流1.3标仓库 - SD", "project": "PRJ-HL-13", "label": "合流1.3标仓库"}]
        if entity == "supplier":
            if query in {"测试供应商", "SUP-TEST"}:
                return [{"value": "测试供应商", "label": "测试供应商", "supplier_code": "SUP-TEST"}]
            return []
        if entity == "company":
            return [{"value": "STEC (Demo)", "label": "盛拓工程有限公司"}]
        return []


class FakeClient:
    def __init__(
        self,
        *,
        logged_user: str = "buyer@example.com",
        docstatus: int = 1,
        project: str = "PROJ-0010",
    ) -> None:
        self.logged_user = logged_user
        self.docstatus = docstatus
        self.project = project

    def get_logged_user(self) -> ToolResult:
        return ToolResult(ok=True, data=self.logged_user)

    def get_document(self, doctype: str, name: str) -> ToolResult:
        if doctype == "Material Request":
            return ToolResult(ok=True, data={
                "doctype": doctype,
                "name": name,
                "docstatus": self.docstatus,
                "material_request_type": "Purchase",
                "company": "STEC (Demo)",
                "project": self.project,
                "items": [{
                    "name": "MRI-001",
                    "item_code": "MAT-CEM-000008",
                    "item_name": "水泥 42.5 袋装 50kg",
                    "qty": 20,
                    "uom": "包",
                    "schedule_date": "2026-08-10",
                    "warehouse": "合流1.3标仓库 - SD",
                    "project": self.project,
                }],
            })
        raise AssertionError(f"unexpected source doctype: {doctype}")


def make_service(
    *,
    identity: ExternalIdentity = PROCUREMENT_IDENTITY,
    client: FakeClient | None = None,
) -> CapabilityManualService:
    return CapabilityManualService(
        FakeRepository(identity),
        reference_data=FakeReferenceData(),
        client_factory=lambda _user: client or FakeClient(),
    )


def test_procurement_operation_requires_a_source_document() -> None:
    service = make_service()
    result = service.prepare(PrepareOperationRequest(
        operation_id="op.request_for_quotation.from_material_request",
        request_id="rfq-no-source",
        suppliers=["测试供应商"],
    ), REQUEST_IDENTITY)

    assert result["status"] == "needs_input"
    assert result["missing"] == ["source_documents"]
    assert service.repository.pending == {}


def test_wrong_source_doctype_is_blocked_before_reading_erpnext() -> None:
    service = make_service()
    result = service.prepare(PrepareOperationRequest(
        operation_id="op.request_for_quotation.from_material_request",
        request_id="rfq-wrong-source",
        source_documents=[{"doctype": "Purchase Order", "name": "PO-001"}],
        suppliers=["测试供应商"],
    ), REQUEST_IDENTITY)

    assert result["status"] == "blocked"
    assert "Material Request" in result["questions"][0]


def test_rfq_prepare_resolves_supplier_and_freezes_source_lineage() -> None:
    service = make_service()
    result = service.prepare(PrepareOperationRequest(
        operation_id="op.request_for_quotation.from_material_request",
        request_id="rfq-valid",
        source_documents=[{"doctype": "Material Request", "name": "MAT-MR-0001"}],
        suppliers=["SUP-TEST"],
        message="请在周五前报价",
    ), REQUEST_IDENTITY)

    assert result["status"] == "needs_confirmation"
    assert result["resolved"]["suppliers"] == ["测试供应商"]
    pending = service.repository.pending[result["pending_id"]]
    assert pending["tool_call"]["tool"] == "erpnext.buying.create_request_for_quotation_draft"
    assert pending["tool_call"]["arguments"]["items"][0]["material_request_item"] == "MRI-001"
    assert pending["summary"]["source_documents"] == [
        {"doctype": "Material Request", "name": "MAT-MR-0001"}
    ]


def test_draft_source_document_cannot_be_compiled() -> None:
    service = make_service(client=FakeClient(docstatus=0))
    result = service.prepare(PrepareOperationRequest(
        operation_id="op.request_for_quotation.from_material_request",
        request_id="rfq-draft-source",
        source_documents=[{"doctype": "Material Request", "name": "MAT-MR-DRAFT"}],
        suppliers=["测试供应商"],
    ), REQUEST_IDENTITY)

    assert result["status"] == "needs_input"
    assert "当前状态不能执行" in result["error"]
    assert service.repository.pending == {}


def test_erpnext_identity_mismatch_stops_before_source_read() -> None:
    service = make_service(client=FakeClient(logged_user="other@example.com"))
    with pytest.raises(PermissionError, match="身份与当前员工不一致"):
        service.prepare(PrepareOperationRequest(
            operation_id="op.request_for_quotation.from_material_request",
            request_id="rfq-wrong-user",
            source_documents=[{"doctype": "Material Request", "name": "MAT-MR-0001"}],
            suppliers=["测试供应商"],
        ), REQUEST_IDENTITY)


def test_unmanaged_source_project_is_blocked_instead_of_using_employee_default() -> None:
    service = make_service(client=FakeClient(project="UNMANAGED-PROJECT"))
    result = service.prepare(PrepareOperationRequest(
        operation_id="op.request_for_quotation.from_material_request",
        request_id="rfq-unmanaged-project",
        source_documents=[{"doctype": "Material Request", "name": "MAT-MR-0001"}],
        suppliers=["测试供应商"],
    ), REQUEST_IDENTITY)

    assert result["status"] == "blocked"
    assert "无法映射" in result["questions"][0]
    assert service.repository.pending == {}


def test_project_clerk_cannot_discover_procurement_chain_writes() -> None:
    project_identity = ExternalIdentity(
        external_subject="procurement-owner",
        agent_id="nexterp",
        employee_user="buyer@example.com",
        profile_name="material_clerk_agent",
        default_project="PRJ-HL-13",
        allowed_projects=("PRJ-HL-13",),
    )
    service = make_service(identity=project_identity)
    result = service.search(CapabilitySearchRequest(query="采购订单", limit=5), REQUEST_IDENTITY)

    assert result["status"] == "not_found"
    assert result["cards"] == []
