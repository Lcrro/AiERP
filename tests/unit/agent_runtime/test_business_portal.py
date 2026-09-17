from __future__ import annotations

from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from nexterp_agent.workbench.business_portal import BusinessCommandStore
from nexterp_agent.workbench.server import (
    AgentWorkbenchService,
    BusinessInputError,
    _BUSINESS_ACCOUNT_CONTEXT,
    document_approval_stages,
    document_quantity_summary,
    document_source_links,
)


ROOT = Path(__file__).resolve().parents[3]


def test_business_command_store_binds_identity_and_replays_request() -> None:
    store = BusinessCommandStore(ttl_seconds=60)
    command = store.create(
        action="material_request.create_draft",
        user="mao.xiaoquan@stec-up.local",
        project="PRJ-HL-13",
        payload={"items": [{"item_code": "1000055201001", "qty": 1}]},
        summary={"title": "创建材料申请草稿"},
    )
    assert store.get(command.command_id, user="mao.xiaoquan@stec-up.local").project == "PRJ-HL-13"
    with pytest.raises(ValueError, match="not found"):
        store.get(command.command_id, user="warehouse.test@stec-up.local")
    store.remember_request("request-1", {"name": "MAT-MR-1"})
    assert store.request_result("request-1") == {"name": "MAT-MR-1"}


def test_business_command_store_isolates_preview_and_idempotency_by_account() -> None:
    store = BusinessCommandStore(ttl_seconds=60)
    command = store.create(
        action="material_request.create_draft",
        user="mao.xiaoquan@stec-up.local",
        project="PRJ-HL-13",
        payload={},
        summary={},
        account_code="classification_v4",
    )
    with pytest.raises(ValueError, match="not found"):
        store.get(command.command_id, user="mao.xiaoquan@stec-up.local", account_code="material_test")
    store.remember_request("request-1", {"account": "classification_v4"}, account_code="classification_v4")
    assert store.request_result("request-1", account_code="material_test") is None
    assert store.request_result("request-1", account_code="classification_v4") == {"account": "classification_v4"}


def test_business_command_store_rejects_unknown_low_level_action() -> None:
    store = BusinessCommandStore()
    with pytest.raises(ValueError, match="unsupported"):
        store.create(action="erpnext.raw_call", user="user@example.com", project="PRJ-HL-13", payload={}, summary={})


def test_business_portal_has_no_ai_navigation_and_preserves_old_workbench_route() -> None:
    portal = (ROOT / "tools" / "business_portal.html").read_text(encoding="utf-8")
    assert "/developer/agent-workbench" not in portal
    assert "物资业务门户 · 内部使用" in portal
    assert "NO AI REQUIRED" not in portal
    assert 'class="portal-nav function-nav"' in portal
    assert 'role="dialog"' in portal and 'aria-modal="true"' in portal
    assert "物料采购申请" in portal
    assert "参考目录" in portal
    assert "物料分类工作台" in portal
    assert "classificationWorkbenchLink" in portal
    server = (ROOT / "src" / "nexterp_agent" / "workbench" / "server.py").read_text(encoding="utf-8")
    assert 'parsed.path in {"/developer/agent-workbench", "/developer/agent-workbench/"}' in server
    assert "/api/business/commands/preview" in server


def test_material_test_bootstrap_is_fixed_to_sandbox_and_has_no_delete() -> None:
    script = (ROOT / "scripts" / "erpnext" / "bootstrap_material_test_business.py").read_text(encoding="utf-8")
    assert 'BASE_URL = "http://localhost:8003"' in script
    assert 'SITE_HOST = "material-test.localhost"' in script
    assert "delete_doc" not in script
    assert "confirm-plan-hash" in script


def test_classification_v4_bootstrap_is_isolated_and_keeps_credentials_stable() -> None:
    script = (ROOT / "scripts" / "erpnext" / "bootstrap_classification_v4_business.py").read_text(encoding="utf-8")
    assert 'SITE = "material-classification-v4.localhost"' in script
    assert 'BASE_URL = "http://127.0.0.1:8004"' in script
    assert 'payload.get("site") == SITE' in script
    assert "Generate only missing user credentials" in script
    assert "MATERIAL_TEST_CREDENTIALS_PATH" not in script


def test_material_test_business_links_resolve_to_actual_sandbox_masters() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "material_test"
    assert service.erpnext_company_name() == "Nexterp物料测试有限公司"

    class FakeClient:
        def search_documents(self, doctype, *, filters, fields, limit, offset=0, order_by=None):
            assert doctype == "Project"
            if filters == {"project_name": "PRJ-HL-13"}:
                return SimpleNamespace(ok=True, data=[{"name": "PROJ-0001", "project_name": "PRJ-HL-13"}])
            return SimpleNamespace(ok=True, data=[])

    assert service.erpnext_project_name(FakeClient(), "PRJ-HL-13") == "PROJ-0001"


def test_business_bootstrap_and_marketplace_keep_identity_and_project_scope() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "material_test"
    visible = service._authorized_business_projects("hu.yinhu@stec-up.local")
    assert visible and {row["project_code"] for row in visible} == {"PRJ-HL-13"}
    warehouse = service._authorized_business_projects("warehouse.test@stec-up.local")
    assert {row["project_code"] for row in warehouse} == {"PRJ-HL-13"}
    portal = (ROOT / "tools" / "workbench" / "business-portal.js").read_text(encoding="utf-8")
    marketplace = (ROOT / "tools" / "workbench" / "material-marketplace.js").read_text(encoding="utf-8")
    assert "请填写退回原因（必填）" in portal
    assert "status_scope" in portal and "date_from" in portal
    assert "todoRank" in portal and "requestedView" in portal
    assert "/api/business/bootstrap" in marketplace
    assert "当前登录员工" in marketplace
    assert "material_request.update_draft" in portal
    assert "material_request.copy" in portal
    assert "quotation.create" in portal
    assert "purchase_order.create" in portal
    assert "查看单据" in portal and "approval-flow" in portal
    assert "待主管审批" in portal and "待项目经理审批" in portal
    assert "group_variants" in marketplace
    assert "openVariantSelector" in marketplace
    assert "variantAttributes" in marketplace
    assert "AbortController" in marketplace
    assert "ERPNext 当前离线" in marketplace
    assert "分类预览（不可申请）" in marketplace
    assert "classification_source" in marketplace
    assert "group_all_multi_sku_types" in (ROOT / "src" / "nexterp_agent" / "workbench" / "server.py").read_text(encoding="utf-8")
    assert "只展示已存在 SKU" in marketplace
    assert "filterInventoryItem" in (ROOT / "tools" / "business_portal.html").read_text(encoding="utf-8")


def test_classification_context_cookie_selects_chatgpt_release() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "material_test"
    context = service.business_context("nexterp_classification_source=chatgpt_v4")
    assert context["classification_source"] == "chatgpt_v4"
    assert context["classification"]["sku_count"] == 917


def test_classification_source_maps_to_isolated_business_account() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "material_test"
    original = service._business_account_for_source("original")
    v4 = service._business_account_for_source("chatgpt_v4")
    assert original["code"] == "material_test"
    assert original["site"] == "material-test.localhost"
    assert v4["code"] == "classification_v4"
    assert v4["site"] == "material-classification-v4.localhost"
    assert v4["classification_source"] == "chatgpt_v4"


def test_business_context_account_cookie_is_authoritative() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "material_test"
    context = service.business_context(
        "nexterp_business_account=classification_v4; nexterp_classification_source=original"
    )
    assert context["classification_source"] == "chatgpt_v4"
    assert context["account"]["code"] == "classification_v4"


def test_document_list_workers_keep_the_selected_business_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parallel document reads must not silently fall back to material-test."""

    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "material_test"
    service._project_name_cache = {}
    seen_accounts: list[str] = []

    class FakeClient:
        def call_method(self, *_args, **_kwargs):
            raise AttributeError("legacy sandbox")

        def search_documents(self, doctype, *, filters, fields, limit, offset=0, order_by=None):
            return SimpleNamespace(ok=True, data=[{"name": "MAT-MR-V4", "docstatus": 0, "status": "Draft"}])

        def get_document(self, doctype, name):
            return SimpleNamespace(ok=True, data={"name": name, "items": [{"project": "PROJ-0001"}]})

    def fake_client(_user: str, account_code: str = "") -> FakeClient:
        seen_accounts.append(account_code or _BUSINESS_ACCOUNT_CONTEXT.get())
        return FakeClient()

    monkeypatch.setattr(service, "client", fake_client)
    token = _BUSINESS_ACCOUNT_CONTEXT.set("classification_v4")
    try:
        result = service.documents("mao.xiaoquan@stec-up.local", "PRJ-HL-13", doctype="Material Request")
    finally:
        _BUSINESS_ACCOUNT_CONTEXT.reset(token)

    group = result["modules"][0]["groups"][0]
    assert [row["name"] for row in group["documents"]] == ["MAT-MR-V4"]
    assert seen_accounts and set(seen_accounts) == {"classification_v4"}


def test_material_marketplace_cards_fill_their_grid_column() -> None:
    stylesheet = (ROOT / "tools" / "workbench" / "material-marketplace.css").read_text(encoding="utf-8")

    assert ".site-header { position: sticky; top: 0; z-index: 30; background: var(--paper);" in stylesheet
    assert ".product-title { display: grid; grid-template-rows: auto auto auto; align-content: start; width: 100%; min-width: 0;" in stylesheet
    assert "grid-row: span 5; grid-template-rows: subgrid;" in stylesheet
    assert ".variant-group-card .product-plate" not in stylesheet
    assert ".product-attributes { display: flex; align-content: flex-start; align-items: flex-start;" in stylesheet


def test_business_document_visibility_excludes_cancelled_and_finished_receipts() -> None:
    matcher = AgentWorkbenchService._document_row_matches_scope
    assert matcher({"name": "PO-1", "docstatus": 1, "status": "To Receive", "per_received": 40}, doctype="Purchase Order", status_scope="pending_receipt")
    assert not matcher({"name": "PO-2", "docstatus": 1, "status": "Completed", "per_received": 100}, doctype="Purchase Order", status_scope="pending_receipt")
    assert not matcher({"name": "PO-3", "docstatus": 2, "status": "Cancelled"}, doctype="Purchase Order", status_scope="active")
    assert matcher({"name": "PO-3", "docstatus": 2, "status": "Cancelled"}, doctype="Purchase Order", status_scope="cancelled")
    assert matcher({"name": "MR-1", "docstatus": 1, "title": "照明采购"}, doctype="Material Request", status_scope="active", query="照明")
    assert not matcher({"name": "MR-1", "docstatus": 1, "title": "照明采购"}, doctype="Material Request", status_scope="active", query="水泥")


def test_inventory_project_context_is_explicit_and_rejects_cross_project_filter() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.business_context = lambda _cookie="": {"user": "warehouse.test@stec-up.local", "project_code": "PRJ-HL-13"}
    with pytest.raises(PermissionError, match="库存项目必须使用当前已授权项目上下文"):
        service.business_inventory("", project="PRJ-OTHER")


def test_document_detail_helpers_preserve_quantities_and_explicit_source_chain() -> None:
    document = {
        "name": "PUR-ORD-1",
        "items": [{
            "qty": 10,
            "received_qty": 4,
            "returned_qty": 1,
            "uom": "件",
            "material_request": "MAT-MR-1",
            "request_for_quotation": "PUR-RFQ-1",
        }],
    }
    assert document_quantity_summary(document) == {
        "line_count": 1,
        "ordered_qty": 10.0,
        "received_qty": 4.0,
        "returned_qty": 1.0,
        "remaining_qty": 7.0,
        "uoms": ["件"],
    }
    assert {(row["doctype"], row["name"]) for row in document_source_links(document)} == {
        ("Material Request", "MAT-MR-1"),
        ("Request for Quotation", "PUR-RFQ-1"),
    }


def test_material_request_approval_stages_follow_erpnext_workflow_state() -> None:
    stages = document_approval_stages(
        "Material Request",
        {"docstatus": 0, "workflow_state": "Nexterp项目审批"},
    )
    assert [row["label"] for row in stages] == ["申请提交", "材料设备主管审批", "项目经理审批", "审批完成"]
    assert [row["status"] for row in stages] == ["completed", "completed", "current", "pending"]
    assert stages[2]["role"] == "项目经理"

    approved = document_approval_stages(
        "Material Request",
        {"docstatus": 1, "workflow_state": "Nexterp已批准"},
    )
    assert {row["status"] for row in approved} == {"completed"}
    assert document_approval_stages("Purchase Order", {"docstatus": 1}) == []


def test_related_source_links_follow_material_request_downstream() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)

    class FakeClient:
        documents = {
            "Request for Quotation": {"name": "RFQ-1", "items": [{"material_request": "MR-1"}]},
            "Supplier Quotation": {"name": "SQ-1", "items": [{"material_request": "MR-1"}]},
            "Purchase Order": {"name": "PO-1", "items": [{"material_request": "MR-1"}]},
        }

        def search_documents(self, doctype, *, filters, fields, limit, offset=0, order_by=None):
            value = self.documents.get(doctype)
            return SimpleNamespace(ok=True, data=[{"name": value["name"]}] if value else [])

        def get_document(self, doctype, name):
            value = dict(self.documents.get(doctype, {}))
            return SimpleNamespace(ok=bool(value), data=value)

    links = service.related_document_source_links(FakeClient(), "Material Request", "MR-1", {"name": "MR-1", "items": []})
    assert {(row["doctype"], row["name"]) for row in links} == {
        ("Request for Quotation", "RFQ-1"),
        ("Supplier Quotation", "SQ-1"),
        ("Purchase Order", "PO-1"),
    }


def test_material_request_preview_freezes_resolved_links_and_uom() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "material_test"
    service.business_commands = BusinessCommandStore()
    service.business_context = lambda _cookie="": {
        "user": "mao.xiaoquan@stec-up.local",
        "project_code": "PRJ-HL-13",
        "project": {"warehouse_code": "WH-HL-13"},
    }
    service.erpnext_company_name = lambda _code="STEC": "Nexterp物料测试有限公司"
    service.erpnext_project_name = lambda _client, _code: "PROJ-0001"

    class FakeClient:
        def document_exists(self, doctype, name):
            return SimpleNamespace(ok=True, data={"exists": True})

        def get_document(self, doctype, name):
            if doctype == "Project":
                return SimpleNamespace(ok=True, data={"name": name, "company": "Nexterp物料测试有限公司"})
            return SimpleNamespace(ok=True, data={
                "item_code": name,
                "item_name": "测试物料",
                "stock_uom": "件",
                "disabled": 0,
                "is_stock_item": 1,
                "is_purchase_item": 1,
            })

    service.client = lambda _user: FakeClient()
    command = service.business_preview("", {
        "action": "material_request.create_draft",
        "payload": {
            "schedule_date": "2026-08-21",
            "purpose": "E2E验收",
            "items": [{"item_code": "1000557301001", "qty": 2, "uom": "件"}],
        },
    })
    assert command["summary"]["resolved"]["project"] == "PROJ-0001"
    stored = service.business_commands.get(command["command_id"], user="mao.xiaoquan@stec-up.local")
    assert stored.payload["_prepared_material_request"] is True
    assert stored.payload["items"][0]["warehouse"] == "合流1.3标仓库 - NMT"

    with pytest.raises(BusinessInputError, match="缺少库存单位") as error:
        service.business_preview("", {
            "action": "material_request.create_draft",
            "payload": {
                "schedule_date": "2026-08-21",
                "items": [{"item_code": "1000557301001", "qty": 2}],
            },
        })
    assert error.value.field_path == "items[0].uom"
