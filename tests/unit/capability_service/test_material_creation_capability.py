from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from nexterp_agent.capability_service.catalog import ExternalIdentity
from nexterp_agent.capability_service.models import ExecuteOperationRequest, PrepareOperationRequest, RequestIdentity
from nexterp_agent.capability_service.service import CapabilityManualService
from nexterp_agent.erpnext.schemas import ToolResult


IDENTITY = ExternalIdentity(
    external_subject="openclaw-owner",
    agent_id="nexterp",
    employee_user="manager@example.com",
    profile_name="material_equipment_agent",
    default_project="PRJ-HL-13",
    allowed_projects=("PRJ-HL-13",),
)
REQUEST_IDENTITY = RequestIdentity(
    external_subject=IDENTITY.external_subject,
    agent_id=IDENTITY.agent_id,
    session_key="item-create-session",
)


class ItemCreationRepository:
    def __init__(self) -> None:
        self.pending: dict[str, dict[str, Any]] = {}

    def resolve_identity(self, external_subject: str, agent_id: str = "") -> ExternalIdentity:
        return IDENTITY

    def current_revision(self) -> str:
        return "item-create-test"

    def operation_bundle(self, operation_id: str) -> dict[str, Any]:
        return {
            "operation": {
                "operation_id": operation_id,
                "label": "创建标准物料",
                "tool_name": "erpnext.stock.create_item",
                "compiler_key": "material.create.v1",
            },
            "slots": [],
            "rules": [],
        }

    def create_pending(self, **kwargs: Any) -> dict[str, Any]:
        row = {
            "pending_id": "pending-item-1",
            "operation_id": kwargs["operation_id"],
            "employee_user": kwargs["identity"].employee_user,
            "project_code": kwargs["project_code"],
            "external_subject": kwargs["identity"].external_subject,
            "agent_id": kwargs["identity"].agent_id,
            "session_key": kwargs["session_key"],
            "request_id": kwargs["request_id"],
            "catalog_revision": "item-create-test",
            "tool_call": kwargs["tool_call"],
            "tool_call_hash": "hash",
            "summary": kwargs["summary"],
            "status": "pending",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "result": None,
        }
        self.pending[row["pending_id"]] = row
        return row

    def claim_pending(self, pending_id: str, *, identity: ExternalIdentity, session_key: str) -> dict[str, Any]:
        row = self.pending[pending_id]
        row["status"] = "executing"
        return row

    def finish_pending(self, pending_id: str, *, status: str, result: dict[str, Any]) -> dict[str, Any]:
        self.pending[pending_id]["status"] = status
        self.pending[pending_id]["result"] = result
        return self.pending[pending_id]


class ItemCreationClient:
    def __init__(self) -> None:
        self.created: dict[str, dict[str, Any]] = {}

    def get_logged_user(self) -> ToolResult:
        return ToolResult(ok=True, data=IDENTITY.employee_user)

    def search_documents(self, doctype: str, **kwargs: Any) -> ToolResult:
        if doctype == "Item":
            return ToolResult(ok=True, data=[{"item_code": "FAST-999999"}])
        return ToolResult(ok=True, data=[])

    def document_exists(self, doctype: str, name: str) -> ToolResult:
        return ToolResult(ok=True, data={"exists": True, "name": name})

    def create_document(self, doctype: str, data: dict[str, Any]) -> ToolResult:
        document = {**data, "doctype": doctype, "name": data["item_code"], "docstatus": 0}
        self.created[data["item_code"]] = document
        return ToolResult(ok=True, data=document)

    def get_document(self, doctype: str, name: str) -> ToolResult:
        return ToolResult(ok=True, data=self.created[name])


def test_item_creation_requires_confirmation_then_reads_back_item() -> None:
    repository = ItemCreationRepository()
    client = ItemCreationClient()
    service = CapabilityManualService(
        repository,  # type: ignore[arg-type]
        client_factory=lambda _user: client,  # type: ignore[arg-type]
    )
    prepared = service.prepare(
        PrepareOperationRequest(
            operation_id="op.material.create_item",
            request_id="create-item-1",
            query="内六角螺丝 M9*47 碳钢",
            attributes={"spec": "M9*47", "material": "碳钢", "strength_grade": "8.8"},
            material_family_hint="螺丝/螺栓",
        ),
        REQUEST_IDENTITY,
    )

    assert prepared["status"] == "needs_confirmation"
    assert prepared["summary"]["item_code"] == "FAST-1000000"
    assert prepared["summary"]["sku_name"] == "内六角螺丝 M9*47 碳钢 8.8"
    assert client.created == {}

    executed = service.execute(
        ExecuteOperationRequest(pending_id=prepared["pending_id"]),
        REQUEST_IDENTITY,
    )

    assert executed["status"] == "completed"
    assert executed["result"]["document"]["item_code"] == "FAST-1000000"
    assert executed["result"]["readback"]["mismatches"] == {}
