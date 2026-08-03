from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from nexterp_agent.agent_runtime.business_capabilities.procurement import CapabilityCompilationError
from nexterp_agent.capability_service.compiler import OperationCompilerRegistry
from nexterp_agent.capability_service.procurement_catalog import OPERATION_BY_ID


TODAY = date(2026, 8, 3)


def _bundle(operation_id: str) -> dict[str, Any]:
    seed = OPERATION_BY_ID[operation_id]
    return {
        "operation": {
            "operation_id": operation_id,
            "label": seed.operation_label,
            "tool_name": seed.tool_name,
            "compiler_key": seed.compiler_key,
        },
        "slots": list(seed.slots),
        "rules": [
            {"rule_id": rule_id, "label": label, "message": message}
            for rule_id, label, message in seed.rules
        ],
    }


def _compile(operation_id: str, snapshot: dict[str, Any], intent: dict[str, Any]):
    return OperationCompilerRegistry().compile(_bundle(operation_id), {
        "today": TODAY,
        "runtime_context": {"company": "STEC (Demo)", "project": "PROJ-0010", "warehouse": "合流仓库 - SD"},
        "source_documents": [snapshot],
        "intent": intent,
    })


def test_rfq_compiles_from_submitted_material_request_with_lineage() -> None:
    source = {
        "doctype": "Material Request", "name": "MR-001", "docstatus": 1,
        "material_request_type": "Purchase", "company": "STEC (Demo)",
        "items": [{
            "name": "MRI-001", "item_code": "ITEM-1", "qty": 20, "uom": "包",
            "schedule_date": "2026-08-10", "warehouse": "合流仓库 - SD", "project": "PROJ-0010",
        }],
    }
    result = _compile("op.request_for_quotation.from_material_request", source, {
        "source_documents": [{"doctype": "Material Request", "name": "MR-001"}],
        "suppliers": ["测试供应商"],
    })

    assert result.tool_call is not None
    assert result.tool_call["tool"] == "erpnext.buying.create_request_for_quotation_draft"
    assert result.tool_call["arguments"]["suppliers"] == ["测试供应商"]
    assert result.tool_call["arguments"]["items"][0]["material_request_item"] == "MRI-001"


def test_supplier_quotation_compiles_rates_against_rfq_rows() -> None:
    source = {
        "doctype": "Request for Quotation", "name": "RFQ-001", "docstatus": 1,
        "company": "STEC (Demo)",
        "items": [{
            "name": "RFQI-001", "item_code": "ITEM-1", "qty": 20, "uom": "包",
            "material_request": "MR-001", "material_request_item": "MRI-001",
        }],
    }
    result = _compile("op.supplier_quotation.from_request_for_quotation", source, {
        "source_documents": [{"doctype": "Request for Quotation", "name": "RFQ-001"}],
        "suppliers": ["测试供应商"],
        "valid_till": "2026-08-20",
        "items": [{"source_row": "RFQI-001", "rate": 32}],
    })

    assert result.tool_call is not None
    arguments = result.tool_call["arguments"]
    assert arguments["request_for_quotation"] == "RFQ-001"
    assert arguments["supplier"] == "测试供应商"
    assert arguments["items"][0]["rate"] == 32
    assert arguments["items"][0]["request_for_quotation_item"] == "RFQI-001"


def test_purchase_order_compiles_only_from_valid_submitted_quotation() -> None:
    source = {
        "doctype": "Supplier Quotation", "name": "SQ-001", "docstatus": 1,
        "company": "STEC (Demo)", "supplier": "测试供应商", "valid_till": "2026-08-20",
        "items": [{"name": "SQI-001", "item_code": "ITEM-1", "qty": 20, "uom": "包", "rate": 32}],
    }
    result = _compile("op.purchase_order.from_supplier_quotation", source, {
        "source_documents": [{"doctype": "Supplier Quotation", "name": "SQ-001"}],
        "schedule_date": "2026-08-10",
    })

    assert result.tool_call == {
        "tool": "erpnext.buying.create_purchase_order_from_supplier_quotation_draft",
        "arguments": {
            "supplier_quotation": "SQ-001",
            "transaction_date": "2026-08-03",
            "schedule_date": "2026-08-10",
        },
    }


def test_purchase_receipt_compiles_from_purchase_order() -> None:
    source = {
        "doctype": "Purchase Order", "name": "PO-001", "docstatus": 1,
        "company": "STEC (Demo)", "supplier": "测试供应商",
        "items": [{"name": "POI-001", "item_code": "ITEM-1", "qty": 20, "uom": "包", "warehouse": "合流仓库 - SD"}],
    }
    result = _compile("op.purchase_receipt.from_purchase_order", source, {
        "source_documents": [{"doctype": "Purchase Order", "name": "PO-001"}],
        "posting_date": "2026-08-03",
    })

    assert result.tool_call is not None
    assert result.tool_call["arguments"]["purchase_order"] == "PO-001"
    assert result.tool_call["arguments"]["posting_date"] == "2026-08-03"


def test_full_purchase_return_compiles_from_submitted_receipt() -> None:
    source = {
        "doctype": "Purchase Receipt", "name": "PR-001", "docstatus": 1, "is_return": 0,
        "company": "STEC (Demo)", "supplier": "测试供应商",
        "items": [{"name": "PRI-001", "item_code": "ITEM-1", "qty": 20, "uom": "包", "warehouse": "合流仓库 - SD"}],
    }
    result = _compile("op.purchase_return.from_purchase_receipt", source, {
        "source_documents": [{"doctype": "Purchase Receipt", "name": "PR-001"}],
        "posting_date": "2026-08-03", "full_return": True, "message": "规格不符",
    })

    assert result.tool_call is not None
    assert result.tool_call["arguments"] == {
        "purchase_receipt": "PR-001",
        "posting_date": "2026-08-03",
        "full_return": True,
        "reason": "规格不符",
    }


def test_source_status_is_a_hard_precondition() -> None:
    source = {
        "doctype": "Purchase Order", "name": "PO-DRAFT", "docstatus": 0,
        "company": "STEC (Demo)", "items": [],
    }
    with pytest.raises(CapabilityCompilationError, match="当前状态不能执行"):
        _compile("op.purchase_receipt.from_purchase_order", source, {
            "source_documents": [{"doctype": "Purchase Order", "name": "PO-DRAFT"}],
        })
