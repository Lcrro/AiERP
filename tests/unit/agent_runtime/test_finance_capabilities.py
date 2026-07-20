from __future__ import annotations

from datetime import date

import pytest

from nexterp_agent.agent_runtime.business_capabilities import (
    CapabilityCompilationError,
    FinanceBusinessIntentDraft,
    FinanceCapabilityCompiler,
    FinanceCapabilityGraph,
    verify_finance_result,
)


TODAY = date(2026, 7, 20)


def _loader(documents=None):
    documents = documents or {}

    def load(doctype, name):
        return documents[(doctype, name)]

    return load


def _compile(payload, documents=None, runtime=None):
    intent = FinanceBusinessIntentDraft.from_dict(payload)
    return FinanceCapabilityCompiler(_loader(documents)).compile(
        intent,
        runtime_context=runtime or {"company": "STEC (Demo)"},
        today=TODAY,
    )


def test_graph_exposes_four_finance_goals() -> None:
    cards = FinanceCapabilityGraph().cards()
    assert {card["goal"] for card in cards} == {
        "query_accounts_payable",
        "create_purchase_invoice_from_receipt",
        "create_supplier_payment_from_invoice",
        "cancel_financial_document",
    }
    assert next(card for card in cards if card["goal"] == "query_accounts_payable")["write"] is False


def test_accounts_payable_uses_runtime_company_and_is_read_only() -> None:
    prepared = _compile({"goal": "query_accounts_payable", "to_date": "2026-07-31"})
    assert prepared.write is False
    assert prepared.tool_call == {
        "tool": "erpnext.accounting.accounts_payable",
        "arguments": {"company": "STEC (Demo)", "to_date": "2026-07-31"},
    }


def test_accounts_payable_rejects_reversed_date_range() -> None:
    with pytest.raises(CapabilityCompilationError, match="开始日期"):
        _compile({
            "goal": "query_accounts_payable",
            "from_date": "2026-08-01",
            "to_date": "2026-07-31",
        })


def test_purchase_invoice_requires_user_bill_identity() -> None:
    documents = {("Purchase Receipt", "PRE-001"): {"name": "PRE-001", "docstatus": 1, "company": "STEC (Demo)"}}
    with pytest.raises(CapabilityCompilationError, match="发票号"):
        _compile({
            "goal": "create_purchase_invoice_from_receipt",
            "source_documents": [{"doctype": "Purchase Receipt", "name": "PRE-001"}],
        }, documents)


def test_purchase_invoice_compiles_from_submitted_receipt() -> None:
    documents = {("Purchase Receipt", "PRE-001"): {"name": "PRE-001", "docstatus": 1, "company": "STEC (Demo)"}}
    prepared = _compile({
        "goal": "create_purchase_invoice_from_receipt",
        "source_documents": [{"doctype": "Purchase Receipt", "name": "PRE-001"}],
        "bill_no": "SUP-INV-1001",
        "bill_date": "2026-07-19",
    }, documents)
    assert prepared.tool_call["tool"] == "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft"
    assert prepared.tool_call["arguments"]["purchase_receipt"] == "PRE-001"
    assert prepared.write is True


def test_supplier_payment_uses_outstanding_and_rejects_overpayment() -> None:
    documents = {("Purchase Invoice", "PINV-001"): {
        "name": "PINV-001", "docstatus": 1, "outstanding_amount": 800,
    }}
    prepared = _compile({
        "goal": "create_supplier_payment_from_invoice",
        "source_documents": [{"doctype": "Purchase Invoice", "name": "PINV-001"}],
        "paid_amount": 600,
    }, documents)
    assert prepared.tool_call["tool"] == "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft"
    assert prepared.tool_call["arguments"]["paid_amount"] == 600
    with pytest.raises(CapabilityCompilationError, match="不能超过"):
        _compile({
            "goal": "create_supplier_payment_from_invoice",
            "source_documents": [{"doctype": "Purchase Invoice", "name": "PINV-001"}],
            "paid_amount": 801,
        }, documents)


def test_cancel_financial_document_requires_reason_and_submitted_state() -> None:
    documents = {("Payment Entry", "PAY-001"): {"name": "PAY-001", "docstatus": 1}}
    with pytest.raises(CapabilityCompilationError, match="业务原因"):
        _compile({
            "goal": "cancel_financial_document",
            "source_documents": [{"doctype": "Payment Entry", "name": "PAY-001"}],
        }, documents)
    prepared = _compile({
        "goal": "cancel_financial_document",
        "source_documents": [{"doctype": "Payment Entry", "name": "PAY-001"}],
        "reason": "测试付款录入错误",
    }, documents)
    assert prepared.tool_call["tool"] == "erpnext.accounting.cancel_financial_document"
    assert prepared.tool_call["arguments"]["reason"] == "测试付款录入错误"


def test_verify_payment_preserves_invoice_reference() -> None:
    documents = {
        ("Purchase Invoice", "PINV-001"): {"name": "PINV-001", "docstatus": 1, "outstanding_amount": 800},
        ("Payment Entry", "PAY-001"): {
            "name": "PAY-001",
            "docstatus": 0,
            "references": [{"reference_doctype": "Purchase Invoice", "reference_name": "PINV-001"}],
        },
    }
    prepared = _compile({
        "goal": "create_supplier_payment_from_invoice",
        "source_documents": [{"doctype": "Purchase Invoice", "name": "PINV-001"}],
    }, documents)
    result = verify_finance_result(
        prepared,
        {"ok": True, "data": {"doctype": "Payment Entry", "name": "PAY-001"}},
        _loader(documents),
    )
    assert result["ok"] is True
    assert "purchase_invoice_allocation_preserved" in result["checks"]
