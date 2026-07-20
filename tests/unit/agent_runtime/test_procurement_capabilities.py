from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest

from nexterp_agent.agent_runtime.business_capabilities import (
    BusinessIntentDraft,
    CapabilityCompilationError,
    ProcurementCapabilityCompiler,
    ProcurementCapabilityGraph,
    canonical_tool_call_hash,
    verify_procurement_result,
)


TODAY = date(2026, 7, 20)


def _documents() -> dict[tuple[str, str], dict]:
    return {
        ("Material Request", "MAT-MR-0001"): {
            "doctype": "Material Request",
            "name": "MAT-MR-0001",
            "docstatus": 1,
            "material_request_type": "Purchase",
            "company": "STEC (Demo)",
            "schedule_date": "2026-07-23",
            "items": [{
                "name": "MRI-1",
                "item_code": "SAFE-000001",
                "qty": 100,
                "uom": "双",
                "warehouse": "合流1.3标仓库 - SD",
                "project": "PROJ-0010",
            }],
        },
        ("Request for Quotation", "PUR-RFQ-0001"): {
            "doctype": "Request for Quotation",
            "name": "PUR-RFQ-0001",
            "docstatus": 1,
            "company": "STEC (Demo)",
            "items": [{
                "name": "RFQI-1",
                "item_code": "SAFE-000001",
                "qty": 100,
                "uom": "双",
                "warehouse": "合流1.3标仓库 - SD",
                "material_request": "MAT-MR-0001",
                "material_request_item": "MRI-1",
            }],
        },
        ("Supplier Quotation", "PUR-SQTN-0001"): {
            "doctype": "Supplier Quotation",
            "name": "PUR-SQTN-0001",
            "docstatus": 1,
            "supplier": "测试供应商甲",
            "company": "STEC (Demo)",
            "valid_till": "2026-07-31",
            "items": [{
                "name": "SQI-1",
                "item_code": "SAFE-000001",
                "qty": 100,
                "uom": "双",
                "rate": 3.8,
                "request_for_quotation": "PUR-RFQ-0001",
                "request_for_quotation_item": "RFQI-1",
            }],
        },
        ("Supplier Quotation", "PUR-SQTN-0002"): {
            "doctype": "Supplier Quotation",
            "name": "PUR-SQTN-0002",
            "docstatus": 1,
            "supplier": "测试供应商乙",
            "company": "STEC (Demo)",
            "items": [{"name": "SQI-2", "item_code": "SAFE-000001", "qty": 100, "rate": 4.1}],
        },
        ("Purchase Order", "PUR-ORD-0001"): {
            "doctype": "Purchase Order",
            "name": "PUR-ORD-0001",
            "docstatus": 1,
            "company": "STEC (Demo)",
            "supplier": "测试供应商甲",
            "items": [{"name": "POI-1", "item_code": "SAFE-000001", "qty": 100, "uom": "双"}],
        },
        ("Purchase Receipt", "MAT-PRE-0001"): {
            "doctype": "Purchase Receipt",
            "name": "MAT-PRE-0001",
            "docstatus": 1,
            "company": "STEC (Demo)",
            "supplier": "测试供应商甲",
            "items": [{"name": "PRI-1", "item_code": "SAFE-000001", "qty": 100, "uom": "双"}],
        },
    }


def _compiler(documents: dict[tuple[str, str], dict] | None = None) -> ProcurementCapabilityCompiler:
    store = documents or _documents()

    def load(doctype: str, name: str) -> dict:
        return deepcopy(store[(doctype, name)])

    return ProcurementCapabilityCompiler(load)


def _context() -> dict[str, str]:
    return {
        "company": "STEC (Demo)",
        "project": "PROJ-0010",
        "warehouse": "合流1.3标仓库 - SD",
    }


def test_material_request_compiles_resolved_context_into_rows() -> None:
    intent = BusinessIntentDraft.from_dict({
        "goal": "create_material_request",
        "schedule_date": "2026-07-23",
        "items": [{"item_code": "SAFE-000001", "qty": 100, "uom": "双"}],
        "provenance": {"schedule_date": "user", "items": "resolver"},
    })

    prepared = _compiler().compile(intent, runtime_context=_context(), today=TODAY)

    assert prepared.capability == "material_request.create"
    assert prepared.tool_call == {
        "tool": "erpnext.buying.create_material_request_draft",
        "arguments": {
            "material_request_type": "Purchase",
            "schedule_date": "2026-07-23",
            "company": "STEC (Demo)",
            "items": [{
                "item_code": "SAFE-000001",
                "qty": 100.0,
                "uom": "双",
                "warehouse": "合流1.3标仓库 - SD",
                "project": "PROJ-0010",
                "schedule_date": "2026-07-23",
            }],
        },
    }
    assert prepared.field_sources["schedule_date"] == "user"
    assert len(prepared.confirmation_hash) == 64


def test_rfq_compiler_preserves_material_request_lineage() -> None:
    intent = BusinessIntentDraft.from_dict({
        "goal": "create_rfq_from_material_request",
        "source_documents": [{"doctype": "Material Request", "name": "MAT-MR-0001"}],
        "suppliers": ["测试供应商甲", "测试供应商乙"],
    })

    prepared = _compiler().compile(intent, runtime_context=_context(), today=TODAY)

    assert prepared.tool_call["tool"] == "erpnext.buying.create_request_for_quotation_draft"
    assert prepared.tool_call["arguments"]["transaction_date"] == "2026-07-20"
    assert prepared.tool_call["arguments"]["items"][0]["material_request"] == "MAT-MR-0001"
    assert prepared.tool_call["arguments"]["items"][0]["material_request_item"] == "MRI-1"


def test_supplier_quotation_requires_user_rate_and_keeps_rfq_reference() -> None:
    missing_rate = BusinessIntentDraft.from_dict({
        "goal": "create_supplier_quotation_from_rfq",
        "source_documents": [{"doctype": "Request for Quotation", "name": "PUR-RFQ-0001"}],
        "supplier": "测试供应商甲",
    })
    with pytest.raises(CapabilityCompilationError, match="缺少报价"):
        _compiler().compile(missing_rate, runtime_context=_context(), today=TODAY)

    intent = BusinessIntentDraft.from_dict({
        "goal": "create_supplier_quotation_from_rfq",
        "source_documents": [{"doctype": "Request for Quotation", "name": "PUR-RFQ-0001"}],
        "supplier": "测试供应商甲",
        "items": [{"source_row": "RFQI-1", "rate": 3.8}],
        "valid_till": "2026-07-31",
    })
    prepared = _compiler().compile(intent, runtime_context=_context(), today=TODAY)

    assert prepared.tool_call["arguments"]["transaction_date"] == "2026-07-20"
    assert prepared.tool_call["arguments"]["valid_till"] == "2026-07-31"
    assert prepared.tool_call["arguments"]["items"][0]["request_for_quotation_item"] == "RFQI-1"
    assert prepared.tool_call["arguments"]["items"][0]["rate"] == 3.8


def test_purchase_order_from_quote_can_only_compile_dedicated_tool() -> None:
    intent = BusinessIntentDraft.from_dict({
        "goal": "create_purchase_order_from_supplier_quotation",
        "source_documents": [{"doctype": "Supplier Quotation", "name": "PUR-SQTN-0001"}],
        "schedule_date": "2026-07-24",
    })

    prepared = _compiler().compile(intent, runtime_context=_context(), today=TODAY)

    assert prepared.tool_call == {
        "tool": "erpnext.buying.create_purchase_order_from_supplier_quotation_draft",
        "arguments": {
            "supplier_quotation": "PUR-SQTN-0001",
            "transaction_date": "2026-07-20",
            "schedule_date": "2026-07-24",
        },
    }
    assert "source_lineage_preserved" in prepared.preflight_checks


def test_receipt_and_return_use_source_specific_tools() -> None:
    receipt = _compiler().compile(
        BusinessIntentDraft.from_dict({
            "goal": "create_purchase_receipt_from_purchase_order",
            "source_documents": [{"doctype": "Purchase Order", "name": "PUR-ORD-0001"}],
        }),
        runtime_context=_context(),
        today=TODAY,
    )
    assert receipt.tool_call["tool"] == "erpnext.buying.create_purchase_receipt_from_purchase_order_draft"
    assert receipt.tool_call["arguments"]["posting_date"] == "2026-07-20"

    with pytest.raises(CapabilityCompilationError, match="退货需要指定"):
        _compiler().compile(
            BusinessIntentDraft.from_dict({
                "goal": "create_purchase_return_from_receipt",
                "source_documents": [{"doctype": "Purchase Receipt", "name": "MAT-PRE-0001"}],
            }),
            runtime_context=_context(),
            today=TODAY,
        )

    return_action = _compiler().compile(
        BusinessIntentDraft.from_dict({
            "goal": "create_purchase_return_from_receipt",
            "source_documents": [{"doctype": "Purchase Receipt", "name": "MAT-PRE-0001"}],
            "full_return": True,
            "message": "规格不符",
        }),
        runtime_context=_context(),
        today=TODAY,
    )
    assert return_action.tool_call["tool"] == "erpnext.buying.create_purchase_receipt_return_draft"
    assert return_action.tool_call["arguments"]["full_return"] is True


def test_graph_only_exposes_legal_next_actions_for_current_state() -> None:
    graph = ProcurementCapabilityGraph()
    submitted_quote = _documents()[("Supplier Quotation", "PUR-SQTN-0001")]
    draft_quote = {**submitted_quote, "docstatus": 0}

    submitted = {row["goal"] for row in graph.legal_actions([submitted_quote])}
    draft = {row["goal"] for row in graph.legal_actions([draft_quote])}

    assert "create_purchase_order_from_supplier_quotation" in submitted
    assert "compare_supplier_quotations" in submitted
    assert "create_purchase_order_from_supplier_quotation" not in draft
    assert "compare_supplier_quotations" not in draft


def test_expired_supplier_quotation_cannot_become_purchase_order() -> None:
    documents = _documents()
    documents[("Supplier Quotation", "PUR-SQTN-0001")]["valid_till"] = "2026-06-30"
    compiler = _compiler(documents)
    intent = BusinessIntentDraft.from_dict({
        "goal": "create_purchase_order_from_supplier_quotation",
        "source_documents": [{"doctype": "Supplier Quotation", "name": "PUR-SQTN-0001"}],
    })

    with pytest.raises(CapabilityCompilationError, match="失效"):
        compiler.compile(intent, runtime_context={}, today=date(2026, 7, 20))


def test_confirmation_hash_ignores_audit_metadata_but_detects_business_change() -> None:
    call = {"tool": "erpnext.buying.create_material_request_draft", "arguments": {"items": [{"item_code": "A", "qty": 2}]}}
    with_confirmation = deepcopy(call)
    with_confirmation["arguments"]["confirmation"] = {"confirmed_by": "user@example.com"}
    changed = deepcopy(call)
    changed["arguments"]["items"][0]["qty"] = 3

    assert canonical_tool_call_hash(call) == canonical_tool_call_hash(with_confirmation)
    assert canonical_tool_call_hash(call) != canonical_tool_call_hash(changed)


def test_readback_verifier_checks_supplier_quotation_lineage() -> None:
    prepared = _compiler().compile(
        BusinessIntentDraft.from_dict({
            "goal": "create_purchase_order_from_supplier_quotation",
            "source_documents": [{"doctype": "Supplier Quotation", "name": "PUR-SQTN-0001"}],
        }),
        runtime_context=_context(),
        today=TODAY,
    )
    created = {
        "doctype": "Purchase Order",
        "name": "PUR-ORD-NEW",
        "docstatus": 0,
        "items": [{"supplier_quotation": "PUR-SQTN-0001", "supplier_quotation_item": "SQI-1"}],
    }

    verified = verify_procurement_result(
        prepared,
        {"ok": True, "data": {"doctype": "Purchase Order", "name": "PUR-ORD-NEW"}},
        lambda _doctype, _name: created,
    )

    assert verified["ok"] is True
    assert "supplier_quotation_lineage_preserved" in verified["checks"]


def test_business_intent_rejects_invalid_dates_and_quantities() -> None:
    with pytest.raises(ValueError, match="schedule_date"):
        BusinessIntentDraft.from_dict({"goal": "create_material_request", "schedule_date": "明天"})
    with pytest.raises(ValueError, match="greater than 0"):
        BusinessIntentDraft.from_dict({"goal": "create_material_request", "items": [{"item_code": "A", "qty": 0}]})
