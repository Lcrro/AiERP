from __future__ import annotations

from nexterp_agent.erpnext import ERPNextAdapter
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class AccountingFakeClient:
    def __init__(self) -> None:
        self.calls = []

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("search_documents", doctype, kwargs))
        if doctype == "Sales Invoice":
            return ToolResult(
                ok=True,
                data=[
                    {
                        "name": "SINV-1",
                        "grand_total": 120,
                        "outstanding_amount": 80,
                        "due_date": "2026-06-30",
                        "currency": "USD",
                    }
                ],
            )
        if doctype == "Bank Transaction":
            return ToolResult(ok=True, data=[{"name": "BTX-1", "deposit": 80, "status": "Unreconciled"}])
        if doctype == "Payment Entry":
            return ToolResult(ok=True, data=[{"name": "PAY-1", "paid_amount": 80, "reference_no": "REF-1"}])
        return ToolResult(ok=True, data=[])

    def get_document(self, doctype, name) -> ToolResult:
        self.calls.append(("get_document", doctype, name))
        if doctype == "Report":
            return ToolResult(ok=True, data={"doctype": "Report", "name": name, "report_type": "Script Report"})
        if doctype == "Sales Taxes and Charges Template":
            return ToolResult(
                ok=True,
                data={
                    "name": name,
                    "taxes": [
                        {
                            "charge_type": "On Net Total",
                            "account_head": "VAT - A",
                            "description": "VAT",
                            "rate": 10,
                        }
                    ],
                },
            )
        if doctype in {"Sales Invoice", "Purchase Invoice"}:
            return ToolResult(ok=True, data={
                "doctype": doctype,
                "name": name,
                "docstatus": 1,
                "supplier": "SUP-001" if doctype == "Purchase Invoice" else None,
                "company": "Acme",
                "grand_total": 100,
                "outstanding_amount": 100,
            })
        if doctype == "Purchase Receipt" and name == "PR-001":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Purchase Receipt",
                    "name": "PR-001",
                    "supplier": "SUP-001",
                    "company": "Acme",
                    "currency": "USD",
                    "docstatus": 1,
                    "is_return": 0,
                    "project": "PROJ-001",
                    "cost_center": "Bridge - A",
                    "items": [
                        {
                            "name": "PRI-001",
                            "item_code": "ITEM-001",
                            "item_name": "Test Item",
                            "qty": 10,
                            "returned_qty": 1,
                            "billed_amt": 24,
                            "uom": "Nos",
                            "conversion_factor": 1,
                            "rate": 12,
                            "price_list_rate": 12,
                            "warehouse": "Stores - A",
                            "expense_account": "Cost of Goods Sold - A",
                            "cost_center": "Bridge - A",
                            "project": "PROJ-001",
                            "purchase_order": "PO-001",
                            "purchase_order_item": "POI-001",
                            "description": "Received project material",
                        }
                    ],
                },
            )
        if doctype == "Purchase Receipt" and name == "PR-DRAFT":
            return ToolResult(ok=True, data={"doctype": "Purchase Receipt", "name": "PR-DRAFT", "docstatus": 0, "items": []})
        return ToolResult(ok=True, data={"name": name})

    def run_report(self, report_name, **kwargs) -> ToolResult:
        self.calls.append(("run_report", report_name, kwargs))
        return ToolResult(ok=True, data={"report_name": report_name, "rows": []})

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, **data})

    def update_document(self, doctype, name, data) -> ToolResult:
        self.calls.append(("update_document", doctype, name, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, **data})

    def submit_document(self, doctype, name) -> ToolResult:
        self.calls.append(("submit_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 1})

    def cancel_document(self, doctype, name) -> ToolResult:
        self.calls.append(("cancel_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 2})

    def call_method(self, method, args=None, http_method="POST") -> ToolResult:
        self.calls.append(("call_method", method, args, http_method))
        if method == "agent_bridge.api.reconcile_bank_transaction":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Bank Transaction",
                    "name": args["bank_transaction"],
                    "docstatus": 0,
                    "status": "Reconciled",
                    "matched_count": len(args["matches"]),
                    "allocated_amount": 80,
                    "unallocated_amount": 0,
                },
            )
        if method == "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry":
            return ToolResult(ok=True, data={
                "doctype": "Payment Entry",
                "payment_type": "Pay",
                "party_type": "Supplier",
                "party": "SUP-001",
                "company": "Acme",
                "paid_from": "Creditors - A",
                "paid_to": "Bank - A",
                "paid_amount": args.get("party_amount") or 100,
                "received_amount": args.get("party_amount") or 100,
                "references": [{
                    "reference_doctype": "Purchase Invoice",
                    "reference_name": args["dn"],
                    "allocated_amount": args.get("party_amount") or 100,
                }],
            })
        return ToolResult(ok=True, data={"method": method})


def test_accounting_read_tools_are_read_only() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    assert adapter.execute({"tool": "erpnext.accounting.search_accounts", "arguments": {"company": "Acme"}}).ok
    assert adapter.execute({"tool": "erpnext.accounting.search_budgets", "arguments": {"fiscal_year": "2026"}}).ok
    assert adapter.execute({"tool": "erpnext.accounting.general_ledger", "arguments": {"company": "Acme"}}).ok
    assert adapter.execute({"tool": "erpnext.accounting.accounts_receivable", "arguments": {"company": "Acme"}}).ok
    assert adapter.execute({"tool": "erpnext.accounting.accounts_payable", "arguments": {"company": "Acme"}}).ok
    assert adapter.execute(
        {"tool": "erpnext.accounting.financial_report", "arguments": {"report_name": "Trial Balance", "company": "Acme"}}
    ).ok
    report = adapter.execute({"tool": "erpnext.accounting.general_ledger", "arguments": {"company": "Acme"}})
    assert report.data["risk"]["level"] == "L0"
    assert report.data["report_name"] == "General Ledger"

    assert client.calls == [
        (
            "search_documents",
            "Account",
            {
                "filters": {"company": "Acme"},
                "fields": ["name", "account_name", "company", "parent_account", "root_type", "account_type", "is_group"],
                "limit": 50,
                "offset": 0,
                "order_by": "lft asc",
            },
        ),
        (
            "search_documents",
            "Budget",
            {
                "filters": {"fiscal_year": "2026"},
                "fields": ["name", "company", "budget_against", "fiscal_year", "docstatus"],
                "limit": 50,
                "offset": 0,
                "order_by": "modified desc",
            },
        ),
        ("run_report", "General Ledger", {"filters": {"company": "Acme"}}),
        ("run_report", "Accounts Receivable", {"filters": {"company": "Acme"}}),
        ("run_report", "Accounts Payable", {"filters": {"company": "Acme"}}),
        ("run_report", "Trial Balance", {"filters": {"company": "Acme"}}),
        ("run_report", "General Ledger", {"filters": {"company": "Acme"}}),
    ]


def test_accounting_draft_tools_force_docstatus_zero() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.create_payment_entry_draft",
            "arguments": {"data": {"payment_type": "Receive", "docstatus": 1}},
        }
    )

    assert result.ok
    assert result.data == {
        "doctype": "Payment Entry",
        "name": None,
        "docstatus": 0,
        "status": "Draft",
        "summary": "Created Payment Entry draft.",
        "next_actions": ["review_payment_allocation", "confirm_submit"],
        "risk": {"level": "L3", "requires_confirmation_for_submit": True},
    }
    assert client.calls == [
        (
            "create_document",
            "Payment Entry",
            {"payment_type": "Receive", "docstatus": 0, "doctype": "Payment Entry"},
        )
    ]


def test_accounting_report_requires_company_filter() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute({"tool": "erpnext.accounting.general_ledger", "arguments": {}})

    assert not result.ok
    assert result.error_type == "missing_report_filter"
    assert result.data["missing_filters"] == ["company"]
    assert client.calls == []


def test_accounting_get_report_filters_does_not_run_report() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute({"tool": "erpnext.accounting.get_report_filters", "arguments": {"report_name": "General Ledger"}})

    assert result.ok
    assert result.data["doctype"] == "Report"
    assert result.data["name"] == "General Ledger"
    assert result.data["required_filters"] == ["company"]
    assert "from_date" in result.data["optional_filters"]
    assert result.data["does_not_run_report"] is True
    assert result.data["risk"] == {"level": "L0", "runs_report": False}
    assert client.calls == [("get_document", "Report", "General Ledger")]


def test_accounting_report_rejects_invalid_date_range() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    reversed_range = adapter.execute(
        {
            "tool": "erpnext.accounting.general_ledger",
            "arguments": {"company": "Acme", "from_date": "2026-12-31", "to_date": "2026-01-01"},
        }
    )
    bad_format = adapter.execute(
        {
            "tool": "erpnext.accounting.financial_report",
            "arguments": {"report_name": "Trial Balance", "company": "Acme", "from_date": "2026/01/01"},
        }
    )

    assert not reversed_range.ok
    assert reversed_range.error_type == "validation_error"
    assert reversed_range.data["status"] == "Invalid Date Range"
    assert not bad_format.ok
    assert bad_format.error_type == "validation_error"
    assert bad_format.data["invalid_filter"] == "from_date"
    assert client.calls == []


def test_period_closing_voucher_draft_is_supported_and_guarded() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.create_period_closing_voucher_draft",
            "arguments": {
                "data": {
                    "company": "Acme",
                    "period_start_date": "2026-01-01",
                    "period_end_date": "2026-12-31",
                    "docstatus": 1,
                }
            },
        }
    )

    assert result.ok
    assert result.data == {
        "doctype": "Period Closing Voucher",
        "name": None,
        "docstatus": 0,
        "status": "Draft",
        "summary": "Created Period Closing Voucher draft.",
        "next_actions": ["review_closing_accounts", "review_period", "confirm_submit"],
        "risk": {"level": "L3", "requires_confirmation_for_submit": True},
    }
    assert client.calls == [
        (
            "create_document",
            "Period Closing Voucher",
            {
                "company": "Acme",
                "period_start_date": "2026-01-01",
                "period_end_date": "2026-12-31",
                "docstatus": 0,
                "doctype": "Period Closing Voucher",
            },
        )
    ]


def test_purchase_invoice_from_purchase_receipt_preserves_source_references() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
            "arguments": {
                "purchase_receipt": "PR-001",
                "posting_date": "2026-06-12",
                "bill_no": "BILL-001",
                "bill_date": "2026-06-12",
                "selected_items": [{"purchase_receipt_item": "PRI-001", "qty": 3}],
            },
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Purchase Invoice"
    assert result.data["status"] == "Draft"
    assert result.data["source_purchase_receipt"] == "PR-001"
    assert result.data["source_item_count"] == 1
    assert result.data["risk"] == {"level": "L3", "requires_confirmation_for_submit": True}
    assert client.calls == [
        ("get_document", "Purchase Receipt", "PR-001"),
        (
            "create_document",
            "Purchase Invoice",
            {
                "doctype": "Purchase Invoice",
                "supplier": "SUP-001",
                "company": "Acme",
                "posting_date": "2026-06-12",
                "bill_no": "BILL-001",
                "bill_date": "2026-06-12",
                "currency": "USD",
                "project": "PROJ-001",
                "cost_center": "Bridge - A",
                "items": [
                    {
                        "item_code": "ITEM-001",
                        "qty": 3.0,
                        "received_qty": 3.0,
                        "uom": "Nos",
                        "conversion_factor": 1,
                        "rate": 12,
                        "price_list_rate": 12,
                        "warehouse": "Stores - A",
                        "expense_account": "Cost of Goods Sold - A",
                        "cost_center": "Bridge - A",
                        "project": "PROJ-001",
                        "description": "Received project material",
                        "purchase_receipt": "PR-001",
                        "pr_detail": "PRI-001",
                        "purchase_order": "PO-001",
                        "po_detail": "POI-001",
                    }
                ],
                "docstatus": 0,
            },
        ),
    ]


def test_purchase_invoice_from_purchase_receipt_requires_submitted_receipt() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
            "arguments": {"purchase_receipt": "PR-DRAFT"},
        }
    )

    assert not result.ok
    assert result.error_type == "validation_error"
    assert result.data["status"] == "Not Submitted"
    assert result.data["next_actions"] == ["submit_purchase_receipt", "retry_purchase_invoice_creation"]
    assert client.calls == [("get_document", "Purchase Receipt", "PR-DRAFT")]


def test_purchase_invoice_from_purchase_receipt_blocks_overbilling() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
            "arguments": {"purchase_receipt": "PR-001", "selected_items": [{"purchase_receipt_item": "PRI-001", "qty": 8}]},
        }
    )

    assert not result.ok
    assert result.error_type == "validation_error"
    assert result.data["errors"][0]["type"] == "qty_exceeds_billable"
    assert result.data["errors"][0]["billable_qty"] == 7.0
    assert client.calls == [("get_document", "Purchase Receipt", "PR-001")]


def test_supplier_payment_from_purchase_invoice_uses_erpnext_generated_accounts() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute({
        "tool": "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft",
        "arguments": {
            "purchase_invoice": "PINV-001",
            "posting_date": "2026-07-20",
            "paid_amount": 60,
            "reference_no": "BANK-REF-1",
            "reference_date": "2026-07-20",
        },
    })

    assert result.ok
    assert result.data["doctype"] == "Payment Entry"
    assert result.data["source_purchase_invoice"] == "PINV-001"
    assert result.data["outstanding_before_payment"] == 100
    created = client.calls[-1]
    assert created[0:2] == ("create_document", "Payment Entry")
    payment = created[2]
    assert payment["paid_from"] == "Creditors - A"
    assert payment["paid_to"] == "Bank - A"
    assert payment["references"] == [{
        "reference_doctype": "Purchase Invoice",
        "reference_name": "PINV-001",
        "allocated_amount": 60,
    }]
    assert payment["docstatus"] == 0


def test_supplier_payment_rejects_amount_above_outstanding() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute({
        "tool": "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft",
        "arguments": {"purchase_invoice": "PINV-001", "paid_amount": 101},
    })

    assert not result.ok
    assert result.error_type == "validation_error"
    assert client.calls == [("get_document", "Purchase Invoice", "PINV-001")]


def test_cancel_financial_document_requires_confirmation_and_submitted_document() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute({
        "tool": "erpnext.accounting.cancel_financial_document",
        "arguments": {"doctype": "Purchase Invoice", "name": "PINV-001", "reason": "重复发票"},
    })
    assert not blocked.ok
    assert blocked.error_type == "financial_confirmation_required"

    allowed = adapter.execute({
        "tool": "erpnext.accounting.cancel_financial_document",
        "arguments": {
            "doctype": "Purchase Invoice",
            "name": "PINV-001",
            "reason": "重复发票",
            "confirmation": {
                "confirmed_by": "finance@example.com",
                "confirmed_at": "2026-07-20T10:00:00Z",
                "confirmation_text": "确认冲销采购发票 PINV-001",
                "reason": "重复发票",
            },
        },
    })
    assert allowed.ok
    assert allowed.data["docstatus"] == 2
    assert client.calls[-2:] == [
        ("get_document", "Purchase Invoice", "PINV-001"),
        ("cancel_document", "Purchase Invoice", "PINV-001"),
    ]


def test_financial_submit_requires_confirmation_metadata() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute(
        {"tool": "erpnext.submit_document", "arguments": {"doctype": "Payment Entry", "name": "ACC-PAY-1"}}
    )

    assert not blocked.ok
    assert blocked.error_type == "financial_confirmation_required"
    assert client.calls == []

    allowed = adapter.execute(
        {
            "tool": "erpnext.submit_document",
            "arguments": {
                "doctype": "Payment Entry",
                "name": "ACC-PAY-1",
                "confirmation": {
                    "confirmed_by": "finance@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "确认提交付款 ACC-PAY-1",
                    "reason": "User approved payment submission.",
                },
            },
        }
    )

    assert allowed.ok
    assert client.calls == [("submit_document", "Payment Entry", "ACC-PAY-1")]


def test_prepare_payment_allocation_is_l1_preview() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.prepare_payment_allocation",
            "arguments": {"party_type": "Customer", "party": "CUST-1", "paid_amount": 50},
        }
    )

    assert result.ok
    assert result.data["risk"]["level"] == "L1"
    assert result.data["references"] == [
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": "SINV-1",
            "total_amount": 120,
            "outstanding_amount": 80.0,
            "allocated_amount": 50.0,
            "due_date": "2026-06-30",
            "currency": "USD",
        }
    ]
    assert result.data["unallocated_amount"] == 0.0


def test_prepare_invoice_taxes_uses_template_without_creating_invoice() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.prepare_invoice_taxes",
            "arguments": {
                "invoice_type": "sales",
                "taxes_and_charges": "VAT 10",
                "items": [{"amount": 200}],
            },
        }
    )

    assert result.ok
    assert result.data["risk"]["level"] == "L1"
    assert result.data["estimated_total_tax"] == 20.0
    assert result.data["taxes"][0]["account_head"] == "VAT - A"
    assert client.calls == [("get_document", "Sales Taxes and Charges Template", "VAT 10")]


def test_prepare_bank_reconciliation_is_read_only_candidate_collection() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.prepare_bank_reconciliation",
            "arguments": {"company": "Acme", "bank_account": "Bank - A", "limit": 5},
        }
    )

    assert result.ok
    assert result.data["risk"]["level"] == "L1"
    assert result.data["bank_transactions"][0]["name"] == "BTX-1"
    assert result.data["payment_candidates"][0]["name"] == "PAY-1"


def test_apply_bank_reconciliation_requires_confirmation() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.apply_bank_reconciliation",
            "arguments": {
                "bank_transaction": "BTX-1",
                "matches": [{"payment_document": "Payment Entry", "payment_entry": "PAY-1", "allocated_amount": 80}],
            },
        }
    )

    assert not result.ok
    assert result.error_type == "financial_confirmation_required"
    assert result.data["risk"]["level"] == "L5_FINANCIAL"
    assert client.calls == []


def test_apply_bank_reconciliation_calls_bridge_with_stable_l5_shape() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.apply_bank_reconciliation",
            "arguments": {
                "bank_transaction": "BTX-1",
                "matches": [{"payment_document": "Payment Entry", "payment_entry": "PAY-1", "allocated_amount": 80}],
                "replace_existing": True,
                "remarks": "Reviewed against bank statement.",
                "confirmation": {
                    "confirmed_by": "finance@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "确认对账 BTX-1 匹配 PAY-1",
                    "reason": "Reviewed bank statement and payment reference.",
                },
            },
        }
    )

    assert result.ok
    assert result.data == {
        "doctype": "Bank Transaction",
        "name": "BTX-1",
        "docstatus": 0,
        "status": "Reconciled",
        "summary": "Applied bank reconciliation for Bank Transaction BTX-1.",
        "matched_count": 1,
        "allocated_amount": 80,
        "unallocated_amount": 0,
        "next_actions": ["audit_bank_reconciliation", "review_bank_transaction"],
        "risk": {
            "level": "L5_FINANCIAL",
            "requires_confirmation_for_submit": False,
            "confirmation_checked": True,
        },
    }
    assert client.calls == [
        (
            "call_method",
            "agent_bridge.api.reconcile_bank_transaction",
            {
                "bank_transaction": "BTX-1",
                "matches": [{"payment_document": "Payment Entry", "payment_entry": "PAY-1", "allocated_amount": 80}],
                "replace_existing": True,
                "remarks": "Reviewed against bank statement.",
            },
            "POST",
        )
    ]


def test_budget_create_and_update_force_draft_docstatus() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    created = adapter.execute(
        {
            "tool": "erpnext.accounting.create_budget_draft",
            "arguments": {"data": {"company": "Acme", "fiscal_year": "2026", "docstatus": 1}},
        }
    )
    updated = adapter.execute(
        {
            "tool": "erpnext.accounting.update_budget_draft",
            "arguments": {"name": "BUD-1", "data": {"fiscal_year": "2027", "docstatus": 1}},
        }
    )

    assert created.ok
    assert updated.ok
    assert created.data["risk"]["level"] == "L3"
    assert updated.data["risk"]["level"] == "L3"
    assert client.calls == [
        ("create_document", "Budget", {"company": "Acme", "fiscal_year": "2026", "docstatus": 0, "doctype": "Budget"}),
        ("update_document", "Budget", "BUD-1", {"fiscal_year": "2027", "docstatus": 0}),
    ]


def test_financial_bridge_submit_requires_confirmation_metadata() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute(
        {
            "tool": "erpnext.call_method",
            "arguments": {
                "method": "agent_bridge.api.submit_document",
                "args": {"doctype": "Sales Invoice", "name": "SINV-1"},
            },
        }
    )

    assert not blocked.ok
    assert blocked.error_type == "financial_confirmation_required"
    assert client.calls == []


def test_accounting_submit_financial_document_is_l5_and_stable_shape() -> None:
    client = AccountingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.accounting.submit_financial_document",
            "arguments": {
                "doctype": "Journal Entry",
                "name": "ACC-JV-1",
                "confirmation": {
                    "confirmed_by": "finance@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "确认提交凭证 ACC-JV-1",
                    "reason": "Reviewed by finance.",
                },
            },
        }
    )

    assert result.ok
    assert result.data == {
        "doctype": "Journal Entry",
        "name": "ACC-JV-1",
        "docstatus": 1,
        "status": "Submitted",
        "summary": "Submitted Journal Entry.",
        "next_actions": ["audit_posting", "review_gl_impact"],
        "risk": {"level": "L5_FINANCIAL", "requires_confirmation_for_submit": True},
    }
    assert client.calls == [("submit_document", "Journal Entry", "ACC-JV-1")]


def test_accounting_tools_infer_expected_risk_levels() -> None:
    assert ToolCall.from_dict({"tool": "erpnext.accounting.general_ledger"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.get_report_filters"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.create_sales_invoice_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.create_period_closing_voucher_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.prepare_payment_allocation"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.prepare_invoice_taxes"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.prepare_bank_reconciliation"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.apply_bank_reconciliation"}).risk_level == "L5_FINANCIAL"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.create_budget_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.update_budget_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.submit_financial_document"}).risk_level == "L5_FINANCIAL"
    assert ToolCall.from_dict({"tool": "erpnext.accounting.cancel_financial_document"}).risk_level == "L5_FINANCIAL"
    assert ToolCall.from_dict({"tool": "erpnext.submit_document", "arguments": {"doctype": "Payment Entry"}}).risk_level == "L5_FINANCIAL"
    assert ToolCall.from_dict({"tool": "erpnext.submit_document"}).risk_level == "L4"
