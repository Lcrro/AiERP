from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "agent_workbench.py"
SPEC = importlib.util.spec_from_file_location("agent_workbench", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_employee_catalog_does_not_expose_credentials() -> None:
    employees = MODULE.employee_catalog()

    assert len(employees) == 8
    assert all("api_key" not in employee and "api_secret" not in employee for employee in employees)
    assert {employee["employee_name"] for employee in employees} >= {"张振光", "潘丰", "毛晓泉", "胡银虎", "方文倩"}


def test_runtime_explorer_is_served_from_a_separate_auditable_page() -> None:
    html = MODULE.RUNTIME_EXPLORER_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "runtime-explorer.js").read_text(encoding="utf-8")

    assert "Agent 运行剖面" in html
    assert 'id="flowMap"' in html
    assert 'id="traceTimeline"' in html
    assert 'id="diagnosis"' in html
    assert "/api/session?" in script
    assert "不包含模型隐藏思维过程" in script
    assert "renderDiagnosis" in script


def test_operation_model_explorer_shows_relational_slot_prototype() -> None:
    html = MODULE.OPERATION_MODEL_PATH.read_text(encoding="utf-8")
    script = (MODULE.ASSET_DIR / "operation-model.js").read_text(encoding="utf-8")

    assert "字段槽位与操作模型" in html
    assert 'id="slotRows"' in html
    assert 'id="toolCall"' in html
    assert 'id="project"></select>' in html
    assert 'id="itemSearch"' in html
    assert "/api/operation-model/material-request" in script
    assert "/api/operation-model/options" in script
    assert "/api/operation-model/compile" in script


def test_result_document_links_build_internal_workbench_route() -> None:
    result = {
        "tool_result": {"data": {"doctype": "Material Request", "name": "MAT-MR-2026-00001"}},
        "tool_results": [],
    }

    assert MODULE.result_document_links(result, "http://localhost:8002") == [
        {
            "doctype": "Material Request",
            "name": "MAT-MR-2026-00001",
            "url": "#document/Material%20Request/MAT-MR-2026-00001",
        }
    ]


def test_pending_confirmation_history_is_explicitly_not_created() -> None:
    result = MODULE.compact_chat_result(
        {
            "status": "needs_confirmation",
            "message": "创建材料申请草稿",
            "pending_tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}},
        },
        "http://localhost:8002",
    )

    assert result["message"] == "我已准备好创建材料申请草稿，但尚未写入 ERPNext。请确认后再执行。"


def test_compact_candidate_keeps_governed_reference_price() -> None:
    candidates = MODULE.compact_chat_candidates([{
        "item_code": "MAT-CEM-000008",
        "sku_name": "水泥 42.5 袋装 50kg",
        "stock_uom": "包",
        "estimated_rate": "28.00",
        "currency": "CNY",
        "price_basis": "测试参考价",
        "data": {"private": "discard"},
    }])

    assert candidates == [{
        "item_code": "MAT-CEM-000008",
        "sku_name": "水泥 42.5 袋装 50kg",
        "stock_uom": "包",
        "estimated_rate": "28.00",
        "currency": "CNY",
        "price_basis": "测试参考价",
    }]


def test_successful_document_is_not_shown_failed_when_final_reply_failed() -> None:
    tool_result = {
        "ok": True,
        "data": {"doctype": "Material Request", "name": "MAT-MR-2026-00015"},
    }

    result = MODULE.compact_chat_result(
        {
            "status": "failed",
            "message": "DeepSeek规划失败：finish.arguments.message is required",
            "tool_result": tool_result,
            "tool_results": [tool_result],
        },
        "http://localhost:8002",
    )

    assert result["status"] == "completed"
    assert "MAT-MR-2026-00015 已在 ERPNext 中执行成功" in result["message"]


def test_business_error_card_explains_precondition_and_next_action() -> None:
    result = MODULE.compact_chat_result(
        {
            "status": "failed",
            "message": "无法创建询价单。",
            "steps": [{
                "result": {
                    "type": "business_action_error",
                    "error": "Material Request MAT-MR-0001 当前状态不能执行询价。",
                },
            }],
        },
        "http://localhost:8002",
    )

    assert result["business_errors"] == [{
        "category": "business_precondition",
        "title": "当前业务状态不允许这样操作",
        "summary": "Material Request MAT-MR-0001 当前状态不能执行询价。",
        "next_actions": ["请先处理来源单据状态或选择符合条件的单据。"],
        "retryable": True,
    }]


def test_business_error_card_preserves_specific_clarification_question() -> None:
    cards = MODULE.business_error_cards({
        "status": "needs_clarification",
        "steps": [{
            "result": {
                "type": "business_action_error",
                "error": "询价单缺少候选供应商。",
                "questions": ["请选择至少一家要询价的供应商。"],
            },
        }],
    })

    assert cards[0]["category"] == "missing_information"
    assert cards[0]["next_actions"] == ["请选择至少一家要询价的供应商。"]


def test_document_process_without_workflow_explains_direct_submission() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "status": "Draft", "_assign": "[]"},
    )

    assert process["state"] == "草稿"
    assert process["workflow_configured"] is False
    assert process["can_submit"] is True
    assert "直接成为已提交状态" in process["description"]
    assert process["notification"] == "当前没有审批待办接收人"


def test_document_process_shows_workflow_state_and_assignees() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "workflow_state": "等待项目经理审批", "_assign": '["manager@example.com"]'},
    )

    assert process["state"] == "等待项目经理审批"
    assert process["workflow_configured"] is True
    assert process["assignees"] == ["manager@example.com"]
    assert process["notification"] == "已生成审批分配"


def test_document_process_exposes_only_current_users_workflow_actions() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "workflow_state": "待材料设备主管审批", "_assign": "[]"},
        ["批准", "驳回"],
    )

    assert process["available_actions"] == ["批准", "驳回"]
    assert process["can_submit"] is False
    assert process["notification"] == "当前账号可执行：批准、驳回"


def test_workbench_workflow_button_executes_erpnext_directly_without_agent() -> None:
    calls = []

    class FakeClient:
        def get_workflow_actions(self, doctype, name):
            calls.append(("get_workflow_actions", doctype, name))
            return SimpleNamespace(ok=True, data=[{"action": "提交申请"}], user_message=None, error=None)

        def call_method(self, method, arguments):
            calls.append(("call_method", method, arguments))
            return SimpleNamespace(ok=True, data={"name": arguments["name"]}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.document = lambda user, doctype, name: {"doctype": doctype, "name": name, "user": user}

    result = service.apply_workflow_action(
        "clerk@example.com",
        "Material Request",
        "MAT-MR-0001",
        "提交申请",
    )

    assert result["name"] == "MAT-MR-0001"
    assert calls == [
        ("get_workflow_actions", "Material Request", "MAT-MR-0001"),
        (
            "call_method",
            "agent_bridge.api.apply_workflow_action_with_comment",
            {"doctype": "Material Request", "name": "MAT-MR-0001", "action": "提交申请", "comment": ""},
        ),
    ]


def test_direct_submit_rejects_documents_with_workflow() -> None:
    class FakeClient:
        def get_document(self, doctype, name):
            return SimpleNamespace(
                ok=True,
                data={"doctype": doctype, "name": name, "workflow_state": "草稿"},
                user_message=None,
                error=None,
            )

        def submit_document(self, _doctype, _name):
            raise AssertionError("workflow document must not be submitted directly")

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()

    with pytest.raises(ValueError, match="已启用审批工作流"):
        service.submit_document("clerk@example.com", "Material Request", "MAT-MR-0001")


def test_workbench_rejection_requires_and_forwards_reason() -> None:
    calls = []

    class FakeClient:
        def get_workflow_actions(self, doctype, name):
            return SimpleNamespace(ok=True, data=[{"action": "驳回"}], user_message=None, error=None)

        def call_method(self, method, arguments):
            calls.append((method, arguments))
            return SimpleNamespace(ok=True, data={"name": arguments["name"]}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.document = lambda user, doctype, name: {"doctype": doctype, "name": name, "user": user}

    with pytest.raises(ValueError, match="驳回时必须填写原因"):
        service.apply_workflow_action("manager@example.com", "Material Request", "MR-1", "驳回")

    service.apply_workflow_action(
        "manager@example.com",
        "Material Request",
        "MR-1",
        "驳回",
        comment="规格不明确，请补充。",
    )

    assert calls == [(
        "agent_bridge.api.apply_workflow_action_with_comment",
        {
            "doctype": "Material Request",
            "name": "MR-1",
            "action": "驳回",
            "comment": "规格不明确，请补充。",
        },
    )]


def test_document_includes_workflow_history_and_business_comments() -> None:
    class FakeClient:
        def call_method(self, method, arguments):
            assert method == "agent_bridge.api.get_document_with_workflow_actions"
            return SimpleNamespace(ok=True, data={
                "document": {"name": "MR-1", "docstatus": 0, "workflow_state": "草稿"},
                "actions": [{"action": "提交申请"}],
                "workflow_history": [{"status": "Completed", "completed_by": "manager@example.com"}],
                "workflow_comments": [{"content": "工作流动作：驳回\n原因：请补充规格。"}],
            }, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()

    result = service.document("clerk@example.com", "Material Request", "MR-1")

    assert result["process"]["history"][0]["completed_by"] == "manager@example.com"
    assert "请补充规格" in result["process"]["comments"][0]["content"]


def test_pending_procurement_enriches_remaining_demand_inventory_and_supplier() -> None:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    class FakeClient:
        def get_pending_procurement_items(self, *, project, warehouses, limit):
            assert project == "PROJ-0010"
            assert warehouses == ["合流1.3标仓库 - SD", "中心仓 - SD"]
            assert limit == 500
            return SimpleNamespace(ok=True, data={
                "rows": [{
                    "material_request": "MAT-MR-TEST-1",
                    "material_request_item": "MRI-1",
                    "item_code": "MAT-CEM-000008",
                    "item_name": "水泥 42.5 袋装 50kg",
                    "qty": 20,
                    "ordered_qty": 5,
                    "remaining_qty": 15,
                    "uom": "包",
                    "schedule_date": tomorrow,
                    "warehouse": "合流1.3标仓库 - SD",
                    "project": "PROJ-0010",
                    "rate": 28,
                }],
                "inventory": [{
                    "item_code": "MAT-CEM-000008",
                    "warehouse": "中心仓 - SD",
                    "actual_qty": 8,
                    "reserved_qty": 2,
                }],
                "summary": {"row_count": 1, "remaining_qty": 15},
            }, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.erpnext_project_name = lambda _client, _project: "PROJ-0010"
    service.procurement_inventory_warehouses = lambda _project, include_all=False: [
        "合流1.3标仓库 - SD", "中心仓 - SD"
    ]

    result = service.pending_procurement("buyer@example.com", "PRJ-HL-13")

    row = result["rows"][0]
    assert row["remaining_qty"] == 15
    assert row["urgency"] == "urgent"
    assert row["total_available_qty"] == 6
    assert row["inventory_coverage"] == "shortage"
    assert row["estimated_amount"] == 420
    assert {stock["warehouse"] for stock in row["inventory"]} == {
        "合流1.3标仓库 - SD", "中心仓 - SD"
    }
    assert row["supplier_suggestions"][0]["supplier_name"] == "测试综合供应商"
    assert result["aggregate"][0]["total_remaining_qty"] == 15
    assert result["summary"]["shortage_rows"] == 1


def test_pending_procurement_all_scope_keeps_cross_project_sources() -> None:
    calls = []

    class FakeClient:
        def get_pending_procurement_items(self, *, project, warehouses, limit):
            calls.append((project, warehouses, limit))
            rows = []
            for index, project_name in enumerate(("PROJ-0010", "PROJ-0020"), start=1):
                rows.append({
                    "material_request": f"MR-{index}",
                    "material_request_item": f"MRI-{index}",
                    "item_code": "MAT-CEM-000008",
                    "qty": 5,
                    "ordered_qty": 0,
                    "remaining_qty": 5,
                    "uom": "包",
                    "project": project_name,
                    "schedule_date": "2099-01-01",
                })
            return SimpleNamespace(ok=True, data={"rows": rows, "inventory": [], "summary": {}}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.procurement_inventory_warehouses = lambda _project, include_all=False: ["中心仓 - SD"]

    result = service.pending_procurement("buyer@example.com", "PRJ-HL-13", scope="all")

    assert calls == [(None, ["中心仓 - SD"], 500)]
    assert len(result["rows"]) == 2
    assert result["aggregate"][0]["total_remaining_qty"] == 10
    assert result["aggregate"][0]["projects"] == ["PROJ-0010", "PROJ-0020"]


def test_reset_documents_cancels_submitted_documents_before_deleting() -> None:
    calls = []

    class FakeClient:
        def cancel_document(self, doctype, name):
            calls.append(("cancel", doctype, name))
            return SimpleNamespace(ok=True, user_message=None, error=None)

        def delete_document(self, doctype, name):
            calls.append(("delete", doctype, name))
            return SimpleNamespace(ok=True, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.documents = lambda user, project, **kwargs: {
        "erpnext_project": "PROJ-0010",
        "modules": [{"groups": [
            {"doctype": "Material Request", "documents": [{"name": "MR-1", "docstatus": 1}]},
            {"doctype": "Purchase Invoice", "documents": [{"name": "PI-1", "docstatus": 0}]},
            {"doctype": "Request for Quotation", "documents": [{"name": "RFQ-KEEP", "docstatus": 0}]},
        ]}],
    }
    service.client = lambda user: FakeClient()

    result = service.reset_documents("buyer@example.com", "PRJ-HL-13")

    assert calls == [
        ("delete", "Purchase Invoice", "PI-1"),
        ("delete", "Request for Quotation", "RFQ-KEEP"),
        ("cancel", "Material Request", "MR-1"),
        ("delete", "Material Request", "MR-1"),
    ]
    assert result["deleted_count"] == 3
    assert result["failed_count"] == 0


def test_create_rfq_reloads_pending_rows_and_preserves_material_request_links() -> None:
    calls = []

    class FakeClient:
        def get_document(self, doctype, name):
            assert (doctype, name) == ("Item", "MAT-CEM-000008")
            return SimpleNamespace(ok=True, data={"item_name": "水泥 42.5 袋装 50kg", "stock_uom": "包", "disabled": 0})

        def create_document(self, doctype, data):
            calls.append((doctype, data))
            return SimpleNamespace(ok=True, data={"name": "PUR-RFQ-0001", "docstatus": 0}, status_code=200, raw_status_code=200)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.pending_procurement = lambda *_args, **_kwargs: {"rows": [{
        "material_request": "MAT-MR-1",
        "material_request_item": "MRI-1",
        "item_code": "MAT-CEM-000008",
        "remaining_qty": 15,
        "uom": "包",
        "schedule_date": "2026-07-20",
        "warehouse": "合流1.3标仓库 - SD",
        "project": "PROJ-0010",
    }]}
    service.document = lambda _user, doctype, name: {"doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)

    result = service.create_request_for_quotation(
        "buyer@example.com",
        "PRJ-HL-13",
        ["MAT-MR-1:MRI-1"],
        ["SUP-TEST-A"],
    )

    assert result["name"] == "PUR-RFQ-0001"
    data = calls[0][1]
    assert data["suppliers"] == [{"supplier": "测试建材供应商甲"}]
    assert data["items"][0]["qty"] == 15
    assert data["items"][0]["material_request"] == "MAT-MR-1"
    assert data["items"][0]["material_request_item"] == "MRI-1"


def test_create_supplier_quotation_requires_submitted_rfq_and_preserves_rfq_row() -> None:
    calls = []

    class FakeClient:
        def get_document(self, doctype, name):
            if doctype == "Item":
                return SimpleNamespace(ok=True, data={"item_name": "水泥 42.5 袋装 50kg", "stock_uom": "包", "disabled": 0})
            assert (doctype, name) == ("Request for Quotation", "PUR-RFQ-0001")
            return SimpleNamespace(ok=True, data={
                    "name": name,
                    "docstatus": 1,
                    "suppliers": [{"supplier": "测试建材供应商甲"}],
                    "items": [{
                        "name": "RFQI-1",
                        "item_code": "MAT-CEM-000008",
                        "qty": 15,
                        "uom": "包",
                        "schedule_date": "2026-07-20",
                    }],
                }, user_message=None, error=None)

        def create_document(self, doctype, data):
            calls.append((doctype, data))
            return SimpleNamespace(ok=True, data={"name": "PUR-SQ-0001", "docstatus": 0}, status_code=200, raw_status_code=200)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.document = lambda _user, doctype, name: {"doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)

    result = service.create_supplier_quotation(
        "buyer@example.com",
        "PRJ-HL-13",
        "PUR-RFQ-0001",
        "SUP-TEST-A",
        [{"request_for_quotation_item": "RFQI-1", "rate": 27.5}],
        terms="月结30天",
    )

    assert result["name"] == "PUR-SQ-0001"
    data = calls[0][1]
    assert data["supplier"] == "测试建材供应商甲"
    assert data["items"][0]["request_for_quotation"] == "PUR-RFQ-0001"
    assert data["items"][0]["request_for_quotation_item"] == "RFQI-1"
    assert data["items"][0]["rate"] == 27.5


def test_create_supplier_quotation_rejects_zero_rate() -> None:
    class FakeClient:
        def get_document(self, _doctype, name):
            return SimpleNamespace(ok=True, data={
                "name": name,
                "docstatus": 1,
                "suppliers": [{"supplier": "测试建材供应商甲"}],
                "items": [{"name": "RFQI-1", "item_code": "MAT-CEM-000008", "qty": 1, "uom": "包"}],
            }, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service._idempotency_context = lambda *_args: (None, None)

    with pytest.raises(ValueError, match="单价必须大于 0"):
        service.create_supplier_quotation(
            "buyer@example.com", "PRJ-HL-13", "PUR-RFQ-0001", "SUP-TEST-A",
            [{"request_for_quotation_item": "RFQI-1", "rate": 0}],
        )


def test_create_purchase_order_from_supplier_quotation_uses_specialized_tool(monkeypatch) -> None:
    calls = []

    class FakeAdapter:
        def __init__(self, client):
            assert client == "client"

        def execute(self, call):
            calls.append(call)
            return SimpleNamespace(ok=True, data={"doctype": "Purchase Order", "name": "PO-1"}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    monkeypatch.setattr(sys.modules[service.__class__.__module__], "ERPNextAdapter", FakeAdapter)
    service.client = lambda _user: "client"
    service.document = lambda user, doctype, name: {"user": user, "doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)
    service._remember_idempotent_result = lambda *_args: None

    result = service.create_purchase_order_from_supplier_quotation(
        "buyer@example.com",
        "PRJ-HL-13",
        "SQ-1",
        request_id="req-1",
    )

    assert result["name"] == "PO-1"
    assert result["source_supplier_quotation"] == "SQ-1"
    assert calls[0]["tool"] == "erpnext.buying.create_purchase_order_from_supplier_quotation_draft"
    assert calls[0]["arguments"]["supplier_quotation"] == "SQ-1"


def test_create_purchase_receipt_from_purchase_order_uses_specialized_tool(monkeypatch) -> None:
    calls = []

    class FakeAdapter:
        def __init__(self, client):
            assert client == "client"

        def execute(self, call):
            calls.append(call)
            return SimpleNamespace(ok=True, data={"doctype": "Purchase Receipt", "name": "PR-1"}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    monkeypatch.setattr(sys.modules[service.__class__.__module__], "ERPNextAdapter", FakeAdapter)
    service.client = lambda _user: "client"
    service.document = lambda user, doctype, name: {"user": user, "doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)
    service._remember_idempotent_result = lambda *_args: None

    result = service.create_purchase_receipt_from_purchase_order(
        "storekeeper@example.com",
        "PRJ-HL-13",
        "PO-1",
        selected_items=[{"purchase_order_item": "POI-1", "qty": 2, "warehouse": "Stores - A"}],
        request_id="req-1",
    )

    assert result["name"] == "PR-1"
    assert result["source_purchase_order"] == "PO-1"
    assert calls[0]["tool"] == "erpnext.buying.create_purchase_receipt_from_purchase_order_draft"
    assert calls[0]["arguments"]["selected_items"][0]["qty"] == 2


def test_purchase_receipt_discrepancy_and_return_use_specialized_tools(monkeypatch) -> None:
    calls = []

    class FakeAdapter:
        def __init__(self, client):
            assert client == "client"

        def execute(self, call):
            calls.append(call)
            if call["tool"].endswith("record_purchase_receipt_discrepancy"):
                return SimpleNamespace(ok=True, data={"status": "Discrepancy Recorded"}, user_message=None, error=None)
            return SimpleNamespace(ok=True, data={"doctype": "Purchase Receipt", "name": "RET-1"}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    monkeypatch.setattr(sys.modules[service.__class__.__module__], "ERPNextAdapter", FakeAdapter)
    service.client = lambda _user: "client"
    service.document = lambda user, doctype, name: {"user": user, "doctype": doctype, "name": name}
    service._idempotency_context = lambda *_args: (None, None)
    service._remember_idempotent_result = lambda *_args: None

    discrepancy = service.record_purchase_receipt_discrepancy(
        "storekeeper@example.com", "PRJ-HL-13", "PR-1", "规格不符",
        items=[{"purchase_receipt_item": "PRI-1", "qty": 2}], assigned_to="buyer@example.com",
    )
    returned = service.create_purchase_return_from_receipt(
        "storekeeper@example.com", "PRJ-HL-13", "PR-1", "整批退回",
        items=[{"purchase_receipt_item": "PRI-1", "qty": 2}],
    )

    assert discrepancy["discrepancy"]["status"] == "Discrepancy Recorded"
    assert returned["name"] == "RET-1"
    assert calls[0]["tool"] == "erpnext.buying.record_purchase_receipt_discrepancy"
    assert calls[0]["arguments"]["assigned_to"] == "buyer@example.com"
    assert calls[1]["tool"] == "erpnext.buying.create_purchase_receipt_return_draft"
    assert calls[1]["arguments"]["reason"] == "整批退回"


def test_project_catalog_contains_project_specific_and_organization_employees() -> None:
    projects = {row["project_code"]: row for row in MODULE.project_catalog()}
    names = {row["employee_name"] for row in projects["PRJ-HL-13"]["employees"]}

    assert projects["PRJ-HL-13"]["project_short_name"] == "合流1.3标"
    assert {"张振光", "林乔航", "毛晓泉", "徐溥祺"} <= names
    assert "梁志华" not in names


def test_employee_catalog_exposes_role_focused_workbench_views() -> None:
    employees = {row["employee_name"]: row for row in MODULE.employee_catalog()}

    assert employees["毛晓泉"]["workbench_view"]["default_panel"] == "mine"
    assert employees["潘丰"]["workbench_view"]["recommended_panels"] == ["inbox", "pending", "progress", "exceptions"]
    assert employees["胡银虎"]["workbench_view"]["default_panel"] == "inbox"
    assert MODULE.WORKBENCH_ROLE_VIEWS["采购员"]["default_panel"] == "pending"
    assert MODULE.WORKBENCH_ROLE_VIEWS["仓管员"]["recommended_panels"] == ["progress", "exceptions", "recent"]


def test_session_history_restores_visible_chat_and_reset_clears_context(tmp_path: Path) -> None:
    user = "mao.xiaoquan@stec-up.local"
    store = MODULE.RuntimeSessionStore(tmp_path)
    session = store.load(user, profile="project")
    session.pending_action = {"tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}}}
    session.add_turn({
        "user_text": "帮我采购点水泥",
        "result": {
            "status": "needs_clarification",
            "message": "请选择具体水泥。",
            "questions": ["请选择具体水泥。"],
            "candidates": [{
                "item_code": "MAT-CEM-000011",
                "sku_name": "水泥 PC425 袋装 50kg",
                "stock_uom": "包",
                "required_specs": "强度等级：42.5",
                "search_keywords": "不应传给网页",
            }],
        },
    })
    store.save(session)
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.session_store = store
    service.base_url = "http://localhost:8002"

    history = service.session_history(user)

    assert history["latest_user_text"] == "帮我采购点水泥"
    assert history["turns"][0]["result"]["message"] == "请选择具体水泥。"
    assert history["turns"][0]["result"]["candidates"] == [{
        "item_code": "MAT-CEM-000011",
        "sku_name": "水泥 PC425 袋装 50kg",
        "required_specs": "强度等级：42.5",
        "stock_uom": "包",
    }]
    assert service.reset_session(user) == {"reset": True, "had_history": True}
    assert service.session_history(user)["turns"] == []


def test_conversations_are_isolated_by_employee_project_and_conversation(tmp_path: Path) -> None:
    user = "mao.xiaoquan@stec-up.local"
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.session_store = MODULE.RuntimeSessionStore(tmp_path)
    service.base_url = "http://localhost:8002"

    first = service.scoped_session_store(user, "PRJ-HL-13", "conversation-a")
    session = first.load(user, profile="project")
    session.add_turn({"user_text": "合流项目要水泥", "result": {"message": "收到"}})
    first.save(session)

    assert service.session_history(user, "PRJ-HL-13", "conversation-a")["turns"]
    assert service.session_history(user, "PRJ-HL-13", "conversation-b")["turns"] == []
    assert service.session_history(user, "PRJ-NJ-01", "conversation-a")["turns"] == []


def test_documents_are_loaded_by_module_with_page_offset() -> None:
    calls = []
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service._project_name_cache = {}
    service.client = lambda _user: object()
    service.erpnext_project_name = lambda _client, _project: "ERP-PROJECT"

    def load_group(user, doctype, label, project_child, project, limit, offset, status, owner):
        calls.append((doctype, limit, offset, status, owner))
        return {"doctype": doctype, "label": label, "documents": []}

    service._load_document_group = load_group
    result = service.documents(
        "buyer@example.com",
        "PRJ-HL-13",
        module="buying",
        status="Draft",
        page=3,
        page_size=10,
        mine_only=True,
    )

    assert result["module"] == "buying"
    assert {call[0] for call in calls} == set(MODULE.MODULE_DOCTYPES["buying"])
    assert all(call[1:] == (10, 20, "Draft", "buyer@example.com") for call in calls)


def test_documents_use_one_module_batch_request_when_bridge_supports_it() -> None:
    calls = []

    class FakeClient:
        def call_method(self, method, arguments):
            calls.append((method, arguments))
            return SimpleNamespace(ok=True, data={
                "groups": {"Material Request": [{"name": "MR-1"}]},
                "errors": {},
            })

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service._project_name_cache = {}
    service.client = lambda _user: FakeClient()
    service.erpnext_project_name = lambda _client, _project: "ERP-PROJECT"
    result = service.documents("buyer@example.com", "PRJ-HL-13", module="buying")

    assert len(calls) == 1
    assert calls[0][0] == "agent_bridge.api.list_workbench_documents"
    assert result["modules"][0]["groups"][0]["documents"] == [{"name": "MR-1"}]


def test_supplier_quotation_project_scope_follows_rfq_and_material_request() -> None:
    documents = {
        ("Supplier Quotation", "SQ-1"): {
            "name": "SQ-1",
            "items": [{
                "request_for_quotation": "RFQ-1",
                "request_for_quotation_item": "RFQI-1",
            }],
        },
        ("Request for Quotation", "RFQ-1"): {
            "name": "RFQ-1",
            "items": [{
                "name": "RFQI-1",
                "material_request": "MR-1",
                "material_request_item": "MRI-1",
            }],
        },
        ("Material Request", "MR-1"): {
            "name": "MR-1",
            "items": [{"name": "MRI-1", "project": "ERP-PROJECT"}],
        },
    }

    class FakeClient:
        def get_document(self, doctype, name):
            document = documents.get((doctype, name))
            return SimpleNamespace(ok=document is not None, data=document)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()

    rows = service.filter_parent_documents_by_project(
        "buyer@example.com",
        "Supplier Quotation",
        [{"name": "SQ-1"}, {"name": "SQ-OTHER"}],
        "ERP-PROJECT",
    )

    assert rows == [{"name": "SQ-1"}]


def test_project_document_filter_uses_one_bridge_request() -> None:
    calls = []

    class FakeClient:
        def call_method(self, method, arguments):
            calls.append((method, arguments))
            return SimpleNamespace(ok=True, data={"names": ["MR-2"]})

        def get_document(self, _doctype, _name):
            raise AssertionError("batch bridge path must not fetch documents one by one")

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    rows = service.filter_parent_documents_by_project(
        "buyer@example.com",
        "Material Request",
        [{"name": "MR-1"}, {"name": "MR-2"}],
        "ERP-PROJECT",
    )

    assert rows == [{"name": "MR-2"}]
    assert calls == [(
        "agent_bridge.api.filter_documents_by_project",
        {
            "doctype": "Material Request",
            "names": ["MR-1", "MR-2"],
            "project": "ERP-PROJECT",
        },
    )]


def test_inbox_uses_open_erpnext_workflow_actions_and_real_transitions() -> None:
    class FakeClient:
        def search_documents(self, doctype, **kwargs):
            assert doctype == "Workflow Action"
            assert kwargs["filters"] == {"status": "Open"}
            return SimpleNamespace(ok=True, data=[{
                "name": "WA-1",
                "reference_doctype": "Material Request",
                "reference_name": "MR-1",
                "workflow_state": "待材料设备主管审批",
                "modified": "2026-07-15 12:00:00",
            }], user_message=None, error=None)

        def call_method(self, method, arguments):
            assert method == "agent_bridge.api.get_document_with_workflow_actions"
            assert arguments == {"doctype": "Material Request", "name": "MR-1"}
            return SimpleNamespace(ok=True, data={
                "document": {"name": "MR-1", "title": "手套申请", "owner": "clerk@example.com"},
                "actions": [{"action": "批准"}, {"action": "驳回"}],
            })

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.erpnext_project_name = lambda _client, _project: ""

    result = service.inbox("supervisor@example.com")

    assert result["count"] == 1
    assert result["items"][0]["actions"] == ["批准", "驳回"]
    assert result["items"][0]["title"] == "手套申请"
