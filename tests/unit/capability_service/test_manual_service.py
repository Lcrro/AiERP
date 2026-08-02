from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from nexterp_agent.capability_service.catalog import ExternalIdentity
from nexterp_agent.capability_service.models import (
    CapabilitySearchRequest,
    ExecuteOperationRequest,
    GuideLoadRequest,
    PrepareOperationRequest,
    RequestIdentity,
)
from nexterp_agent.capability_service.service import CapabilityManualService, parse_schedule_date
from nexterp_agent.erpnext.schemas import ToolResult


IDENTITY_REQUEST = RequestIdentity(
    external_subject="openclaw-owner",
    agent_id="nexterp",
    session_key="session-1",
)
IDENTITY = ExternalIdentity(
    external_subject="openclaw-owner",
    agent_id="nexterp",
    employee_user="material@example.com",
    profile_name="material_clerk_agent",
    default_project="PRJ-HL-13",
    allowed_projects=("PRJ-HL-13",),
)


class FakeRepository:
    def __init__(self) -> None:
        self.pending: dict[str, dict[str, Any]] = {}

    def resolve_identity(self, external_subject: str, agent_id: str = "") -> ExternalIdentity:
        if (external_subject, agent_id) != (IDENTITY.external_subject, IDENTITY.agent_id):
            raise PermissionError("not bound")
        return IDENTITY

    def current_revision(self) -> str:
        return "manual-test"

    def search_nodes(self, query: str, *, module: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        return [{
            "node_id": "op.material_request.create", "node_type": "operation", "module": "buying",
            "label": "创建材料申请草稿", "summary": "创建材料申请", "is_write": True, "score": 100,
        }]

    def load_guides(self, node_ids: list[str]) -> list[dict[str, Any]]:
        return [{
            "node_id": node_id, "node_type": "operation", "module": "buying", "label": "创建材料申请草稿",
            "summary": "创建材料申请", "guide": "先解析后准备", "usage_conditions": "", "prohibitions": "",
            "examples": [], "implementation_key": "material_request.create.v1", "is_write": True, "relations": [],
        } for node_id in node_ids]

    def operation_bundle(self, operation_id: str) -> dict[str, Any]:
        return {"operation": {
            "operation_id": operation_id, "label": "创建材料申请草稿",
            "tool_name": "erpnext.buying.create_material_request_draft",
            "compiler_key": "material_request.create.v1",
        }, "slots": material_request_slots(), "rules": [{"rule_id": "rule.mr.items"}]}

    def create_pending(self, **kwargs: Any) -> dict[str, Any]:
        existing = next((row for row in self.pending.values() if row["request_id"] == kwargs["request_id"]), None)
        if existing:
            return existing
        row = {
            "pending_id": "pending-1", "operation_id": kwargs["operation_id"],
            "employee_user": kwargs["identity"].employee_user, "project_code": kwargs["project_code"],
            "external_subject": kwargs["identity"].external_subject, "agent_id": kwargs["identity"].agent_id,
            "session_key": kwargs["session_key"], "request_id": kwargs["request_id"],
            "catalog_revision": "manual-test", "tool_call": kwargs["tool_call"], "tool_call_hash": "hash",
            "summary": kwargs["summary"], "status": "pending",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15), "result": None,
        }
        self.pending[row["pending_id"]] = row
        return row

    def claim_pending(self, pending_id: str, *, identity: ExternalIdentity, session_key: str) -> dict[str, Any]:
        row = self.pending[pending_id]
        if row["employee_user"] != identity.employee_user or row["session_key"] != session_key:
            raise PermissionError("wrong owner")
        row["status"] = "executing"
        return row

    def get_pending(self, pending_id: str, *, for_update: bool = False) -> dict[str, Any]:
        return self.pending[pending_id]

    def finish_pending(self, pending_id: str, *, status: str, result: dict[str, Any]) -> dict[str, Any]:
        self.pending[pending_id]["status"] = status
        self.pending[pending_id]["result"] = result
        return self.pending[pending_id]


class FakeReferenceData:
    def options(self, entity: str, *, query: str = "", project: str = "", item_code: str = "") -> list[dict[str, Any]]:
        if entity == "company":
            return [{"value": "STEC (Demo)", "label": "盛拓工程有限公司"}]
        if entity == "project":
            return [{"value": "PROJ-0010", "source_code": "PRJ-HL-13", "label": "合流1.3标"}]
        if entity == "warehouse":
            return [{"value": "合流1.3标仓库 - SD", "label": "合流1.3标仓库"}]
        if entity == "item":
            if query == "水泥":
                return [
                    {"value": "MAT-CEM-000008", "label": "水泥 42.5 袋装 50kg", "stock_uom": "包"},
                    {"value": "MAT-CEM-000018", "label": "水泥 42.5 散装", "stock_uom": "吨"},
                ]
            if query == "水泥42.5袋装50kg":
                return [
                    {"value": "MAT-CEM-000008", "label": "水泥 42.5 袋装 50kg", "stock_uom": "包"},
                    {"value": "MAT-CEM-000011", "label": "水泥 PC425 袋装 50kg", "stock_uom": "包"},
                ]
            return [{"value": "MAT-CEM-000008", "label": "水泥 42.5 袋装 50kg", "stock_uom": "包"}]
        if entity == "uom":
            return [{"value": "包", "label": "包"}]
        return []


class FakeReferenceDataWithCentralWarehouse(FakeReferenceData):
    def options(self, entity: str, *, query: str = "", project: str = "", item_code: str = "") -> list[dict[str, Any]]:
        if entity == "warehouse":
            return [
                {"value": "中心仓 - SD", "label": "中心仓", "project": ""},
                {"value": "合流1.3标仓库 - SD", "label": "合流1.3标仓库", "project": "PRJ-HL-13"},
            ]
        return super().options(entity, query=query, project=project, item_code=item_code)


class FakeClient:
    def get_logged_user(self) -> ToolResult:
        return ToolResult(ok=True, data="material@example.com")

    def create_document(self, doctype: str, data: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, data={**data, "doctype": doctype, "name": "MAT-MR-TEST-0001"})

    def get_document(self, doctype: str, name: str) -> ToolResult:
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 0, "status": "Draft"})


class FailingClient(FakeClient):
    def create_document(self, doctype: str, data: dict[str, Any]) -> ToolResult:
        raise ConnectionError("ERPNext unavailable")


def material_request_slots() -> list[dict[str, Any]]:
    def row(
        slot_id: str, label: str, position: int, scope: str, target_path: str,
        source: str, source_path: str | None = None, *, fixed_value: Any = None,
        derived_from: str | None = None,
    ) -> dict[str, Any]:
        return {
            "slot_id": slot_id, "label": label, "description": label, "position": position,
            "scope": scope, "target_path": target_path, "source": source, "control": "select",
            "editable": False, "lookup_doctype": None, "format_hint": None,
            "default_strategy": None, "source_path": source_path, "required": True,
            "resolver": None, "fixed_value": fixed_value, "derived_from": derived_from,
            "constraint": None,
        }

    return [
        row("slot.company", "公司", 1, "document", "arguments.company", "runtime_context", "context.company"),
        row("slot.project", "项目", 2, "document", "context.erpnext_project", "runtime_context", "context.erpnext_project"),
        row("slot.warehouse", "目标仓库", 3, "document", "context.warehouse", "runtime_context", "context.warehouse"),
        row("slot.need_by_date", "需求日期", 4, "document", "arguments.schedule_date", "user_input", "user.schedule_date"),
        row("slot.item_code", "物料编码", 5, "item", "arguments.items[].item_code", "resolver", "items[].item_code"),
        row("slot.quantity", "数量", 6, "item", "arguments.items[].qty", "user_input", "items[].qty"),
        row("slot.uom", "计量单位", 7, "item", "arguments.items[].uom", "user_choice", "items[].uom"),
        row("slot.item_project", "明细项目", 8, "item", "arguments.items[].project", "derived", derived_from="slot.project"),
        row("slot.item_warehouse", "明细仓库", 9, "item", "arguments.items[].warehouse", "derived", derived_from="slot.warehouse"),
        row("slot.item_need_by_date", "明细需求日期", 10, "item", "arguments.items[].schedule_date", "derived", derived_from="slot.need_by_date"),
        row("slot.material_request_type", "申请类型", 11, "document", "arguments.material_request_type", "fixed", fixed_value="Purchase"),
    ]


def service() -> CapabilityManualService:
    return CapabilityManualService(
        FakeRepository(), reference_data=FakeReferenceData(), client_factory=lambda _user: FakeClient(),
    )


def test_capability_search_and_guide_are_role_filtered() -> None:
    manual = service()
    search = manual.search(CapabilitySearchRequest(query="创建材料申请"), IDENTITY_REQUEST)
    guide = manual.load_guides(GuideLoadRequest(node_ids=["op.material_request.create"]), IDENTITY_REQUEST)

    assert search["cards"][0]["node_id"] == "op.material_request.create"
    assert guide["guides"][0]["implementation_key"] == "material_request.create.v1"


def test_ambiguous_item_returns_choices_without_pending_write() -> None:
    manual = service()
    result = manual.prepare(PrepareOperationRequest(
        operation_id="op.material_request.create", request_id="req-1",
        schedule_text="后天", items=[{"raw_item_text": "水泥", "qty": 20}],
    ), IDENTITY_REQUEST)

    assert result["status"] == "needs_choice"
    assert len(result["choices"][0]["candidates"]) == 2
    assert manual.repository.pending == {}


def test_normalized_exact_sku_name_selects_one_candidate() -> None:
    manual = service()
    result = manual.prepare(PrepareOperationRequest(
        operation_id="op.material_request.create", request_id="req-exact-name", schedule_date="2026-08-04",
        items=[{"raw_item_text": "水泥42.5袋装50kg", "qty": 20, "uom": "包"}],
    ), IDENTITY_REQUEST)

    assert result["status"] == "needs_confirmation"
    assert result["summary"]["items"][0]["item_code"] == "MAT-CEM-000008"


def test_requested_uom_must_be_allowed_by_the_resolved_item() -> None:
    manual = service()
    result = manual.prepare(PrepareOperationRequest(
        operation_id="op.material_request.create", request_id="req-invalid-uom", schedule_date="2026-08-04",
        items=[{"item_code": "MAT-CEM-000008", "qty": 20, "uom": "吨"}],
    ), IDENTITY_REQUEST)

    assert result["status"] == "needs_choice"
    assert result["choices"][0]["entity"] == "uom"
    assert result["choices"][0]["requested_uom"] == "吨"
    assert result["choices"][0]["candidates"] == [{"value": "包", "label": "包"}]
    assert manual.repository.pending == {}


def test_resolved_facts_create_immutable_confirmation_and_execute_once() -> None:
    manual = service()
    request = PrepareOperationRequest(
        operation_id="op.material_request.create", request_id="req-2", schedule_date="2026-08-04",
        items=[{"item_code": "MAT-CEM-000008", "qty": 20, "uom": "包"}],
    )
    prepared = manual.prepare(request, IDENTITY_REQUEST)
    repeated = manual.prepare(request, IDENTITY_REQUEST)

    assert prepared["status"] == "needs_confirmation"
    assert repeated["pending_id"] == prepared["pending_id"]
    pending = manual.repository.pending[prepared["pending_id"]]
    assert pending["tool_call"]["arguments"]["items"][0]["item_code"] == "MAT-CEM-000008"

    executed = manual.execute(ExecuteOperationRequest(pending_id=prepared["pending_id"]), IDENTITY_REQUEST)
    assert executed["status"] == "completed"
    assert executed["result"]["document"]["name"] == "MAT-MR-TEST-0001"


def test_prepare_prefers_the_only_warehouse_bound_to_the_resolved_project() -> None:
    manual = CapabilityManualService(
        FakeRepository(),
        reference_data=FakeReferenceDataWithCentralWarehouse(),
        client_factory=lambda _user: FakeClient(),
    )

    prepared = manual.prepare(PrepareOperationRequest(
        operation_id="op.material_request.create",
        request_id="req-project-warehouse",
        schedule_date="2026-08-04",
        items=[{"item_code": "MAT-CEM-000008", "qty": 20, "uom": "包"}],
    ), IDENTITY_REQUEST)

    assert prepared["status"] == "needs_confirmation"
    assert prepared["summary"]["warehouse"] == "合流1.3标仓库 - SD"


def test_pending_is_bound_to_openclaw_session() -> None:
    manual = service()
    prepared = manual.prepare(PrepareOperationRequest(
        operation_id="op.material_request.create", request_id="req-3", schedule_date="2026-08-04",
        items=[{"item_code": "MAT-CEM-000008", "qty": 1, "uom": "包"}],
    ), IDENTITY_REQUEST)

    with pytest.raises(PermissionError):
        manual.execute(
            ExecuteOperationRequest(pending_id=prepared["pending_id"]),
            IDENTITY_REQUEST.model_copy(update={"session_key": "different-session"}),
        )


def test_execution_exception_is_persisted_as_failed_instead_of_staying_executing() -> None:
    manual = CapabilityManualService(
        FakeRepository(), reference_data=FakeReferenceData(), client_factory=lambda _user: FailingClient(),
    )
    prepared = manual.prepare(PrepareOperationRequest(
        operation_id="op.material_request.create", request_id="req-failure", schedule_date="2026-08-04",
        items=[{"item_code": "MAT-CEM-000008", "qty": 1, "uom": "包"}],
    ), IDENTITY_REQUEST)

    result = manual.execute(ExecuteOperationRequest(pending_id=prepared["pending_id"]), IDENTITY_REQUEST)

    assert result["status"] == "failed"
    assert result["result"]["error_type"] == "execution_error"
    assert manual.repository.pending[prepared["pending_id"]]["status"] == "failed"


def test_relative_date_parser_is_deterministic() -> None:
    assert parse_schedule_date("后天", today=date(2026, 8, 2)) == "2026-08-04"
    assert parse_schedule_date("2026-08-06", today=date(2026, 8, 2)) == "2026-08-06"
    assert parse_schedule_date("下礼拜") is None
