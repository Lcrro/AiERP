from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime
from nexterp_agent.agent_runtime.session import RuntimeSessionState, RuntimeSessionStore


def extractor(payload: dict):
    def extract(_: str, *, context=None) -> dict:
        return payload

    return extract


@pytest.mark.parametrize(
    ("payload", "documents", "expected_tool"),
    [
        (
            {"intent": "submit_document", "document_type": "Material Request", "document_name": "", "items": [], "questions": []},
            {"Material Request": ["MAT-MR-2026-00004"]},
            "erpnext.buying.submit_document",
        ),
        (
            {"intent": "create_purchase_order", "supplier_text": "测试综合供应商", "items": [], "questions": []},
            {"Material Request": ["MAT-MR-2026-00004"]},
            "erpnext.buying.create_purchase_order_from_material_request_draft",
        ),
        (
            {"intent": "create_purchase_receipt", "items": [], "questions": []},
            {"Purchase Order": ["PUR-ORD-2026-00001"]},
            "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
        ),
        (
            {
                "intent": "record_receipt_discrepancy",
                "description": "规格与订单不一致",
                "discrepancy_type": "规格不符",
                "full_return": True,
                "items": [],
                "questions": [],
            },
            {"Purchase Receipt": ["MAT-PRE-2026-00001"]},
            "erpnext.buying.record_purchase_receipt_discrepancy",
        ),
        (
            {"intent": "create_purchase_return", "description": "规格不符全部退货", "full_return": True, "items": [], "questions": []},
            {"Purchase Receipt": ["MAT-PRE-2026-00001"]},
            "erpnext.buying.create_purchase_receipt_return_draft",
        ),
        (
            {"intent": "create_purchase_invoice", "items": [], "questions": []},
            {"Purchase Receipt": ["MAT-PRE-2026-00001"]},
            "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
        ),
    ],
)
def test_document_workflows_compile_from_structured_session(
    tmp_path: Path,
    payload: dict,
    documents: dict[str, list[str]],
    expected_tool: str,
) -> None:
    store = RuntimeSessionStore(tmp_path)
    store.save(RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement", documents=documents))
    runtime = CivilAgentRuntime(intent_extractor=extractor(payload), session_store=store)

    result = runtime.run_once("测试业务命令", user="pan.feng@stec-up.local", today=date(2026, 7, 11))

    assert result.status == "needs_confirmation"
    assert result.tool_call["tool"] == expected_tool
    if expected_tool == "erpnext.buying.record_purchase_receipt_discrepancy":
        assert result.tool_call["arguments"]["assigned_to"] == "pan.feng@stec-up.local"


def test_material_issue_compiles_resolved_item_project_and_warehouse(tmp_path: Path) -> None:
    payload = {
        "intent": "create_material_issue",
        "project_text": "合流1.3标",
        "warehouse_text": "合流1.3标仓库",
        "items": [{"raw_item_text": "6.8级螺栓 M12*40", "qty": 5, "uom": "个", "specs": {}}],
        "description": "现场领料",
        "questions": [],
    }
    runtime = CivilAgentRuntime(intent_extractor=extractor(payload), session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("领料", user="mao.xiaoquan@stec-up.local", today=date(2026, 7, 11))

    assert result.status == "needs_confirmation"
    assert result.tool_call["tool"] == "erpnext.projects.create_material_issue_draft"
    assert result.tool_call["arguments"]["items"][0]["item_code"] == "SPARE-000071-68"


def test_runtime_repairs_document_number_omitted_by_model(tmp_path: Path) -> None:
    payload = {
        "intent": "create_purchase_order",
        "document_name": "",
        "supplier_text": "测试综合供应商",
        "items": [],
        "questions": ["模型误以为单号缺失"],
    }
    runtime = CivilAgentRuntime(intent_extractor=extractor(payload), session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once(
        "把材料申请 MAT-MR-2026-00004 转成采购订单",
        user="pan.feng@stec-up.local",
        today=date(2026, 7, 11),
    )

    assert result.status == "needs_confirmation"
    assert result.tool_call["arguments"]["material_request"] == "MAT-MR-2026-00004"


def test_runtime_normalizes_purchase_return_submit_type(tmp_path: Path) -> None:
    payload = {
        "intent": "submit_document",
        "document_type": "Purchase Return",
        "document_name": "MAT-PR-RET-2026-00002",
        "items": [],
        "questions": [],
    }
    runtime = CivilAgentRuntime(intent_extractor=extractor(payload), session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("提交采购退货", user="pan.feng@stec-up.local", today=date(2026, 7, 11))

    assert result.tool_call["tool"] == "erpnext.buying.submit_document"
    assert result.tool_call["arguments"]["doctype"] == "Purchase Receipt"
