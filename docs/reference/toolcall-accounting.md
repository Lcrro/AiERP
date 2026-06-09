# ERPNext Accounting ToolCall Coverage

Scope: Accounting / 财务.

This document records the current ToolCall surface for accounts, general ledger,
receivables/payables, payments, invoices, bank/tax/budget references, and
financial reports.

## Implemented Tools

Read-only accounting queries:

| Tool | ERPNext surface | Notes |
| --- | --- | --- |
| `erpnext.accounting.search_accounts` | `Account` | Query chart of accounts by company, account type, filters, fields, paging, and order. |
| `erpnext.accounting.search_cost_centers` | `Cost Center` | Query cost center tree by company and filters. |
| `erpnext.accounting.search_budgets` | `Budget` | Query budget documents by company, fiscal year, and filters. |
| `erpnext.accounting.search_fiscal_years` | `Fiscal Year` | Query fiscal years by year, disabled flag, filters, fields, paging, and order. |
| `erpnext.accounting.search_accounting_periods` | `Accounting Period` | Query accounting periods by company and date overlap without changing period locks. |
| `erpnext.accounting.search_payment_terms` | `Payment Term`, `Payment Terms Template` | Query payment terms and templates for invoice/payment planning. |
| `erpnext.accounting.search_tax_templates` | Sales/Purchase tax templates | Query sales or purchase tax templates by company, category, status, and title. |
| `erpnext.accounting.get_report_filters` | `Report` metadata plus local contract | Reads the supported filter contract for a standard accounting report without running it. |
| `erpnext.accounting.general_ledger` | `General Ledger` report | Uses `erpnext.run_report` / Frappe query report. |
| `erpnext.accounting.accounts_receivable` | `Accounts Receivable` report | Uses `erpnext.run_report`; read-only aging/open receivable view. |
| `erpnext.accounting.accounts_payable` | `Accounts Payable` report | Uses `erpnext.run_report`; read-only aging/open payable view. |
| `erpnext.accounting.financial_report` | `Trial Balance`, `Balance Sheet`, `Profit and Loss Statement`, `Cash Flow` | Allowlisted report names only. |
| `erpnext.accounting.prepare_payment_allocation` | Payment Entry references | L1 preview; prepares invoice reference rows without creating payment. |
| `erpnext.accounting.prepare_invoice_taxes` | Sales/Purchase tax templates | L1 preview; prepares tax rows and estimated tax, ERPNext validates final draft. |
| `erpnext.accounting.prepare_bank_reconciliation` | Bank Transaction + Payment Entry candidates | L1 read-only reconciliation review; does not match or post. |
| `erpnext.accounting.apply_bank_reconciliation` | Bank Transaction matching | L5_FINANCIAL confirmed wrapper; matches existing payment documents, does not create payments or journal entries. |

Draft-only document creation:

| Tool | ERPNext DocType | Risk | Notes |
| --- | --- | --- | --- |
| `erpnext.accounting.create_journal_entry_draft` | `Journal Entry` | `L3` | Forces `docstatus = 0`; no submit. |
| `erpnext.accounting.create_payment_entry_draft` | `Payment Entry` | `L3` | Forces `docstatus = 0`; no payment submission. |
| `erpnext.accounting.create_sales_invoice_draft` | `Sales Invoice` | `L3` | Forces `docstatus = 0`; no invoice posting. |
| `erpnext.accounting.create_purchase_invoice_draft` | `Purchase Invoice` | `L3` | Forces `docstatus = 0`; no invoice posting. |
| `erpnext.accounting.create_period_closing_voucher_draft` | `Period Closing Voucher` | `L3` | Forces `docstatus = 0`; no period close submission. |
| `erpnext.accounting.create_budget_draft` | `Budget` | `L3` | Forces `docstatus = 0`; no budget submission. |
| `erpnext.accounting.update_budget_draft` | `Budget` | `L3` | Updates a Budget draft and forces `docstatus = 0`. |
| `erpnext.accounting.submit_financial_document` | Financial submittable DocTypes | `L5_FINANCIAL` | Explicit high-risk submit path with confirmation metadata. |

Existing generic tools still apply for read-only supporting data:

| Need | Preferred Tool |
| --- | --- |
| Company lookup | `erpnext.search_documents` on `Company` |
| Bank Account lookup | `erpnext.search_documents` on `Bank Account` |
| Tax Template lookup | `erpnext.accounting.search_tax_templates` |
| Fiscal Year lookup | `erpnext.accounting.search_fiscal_years` |
| Accounting Period lookup | `erpnext.accounting.search_accounting_periods` |
| Payment Term lookup | `erpnext.accounting.search_payment_terms` |
| GL Entry raw rows | Prefer `erpnext.accounting.general_ledger`; use `erpnext.search_documents` on `GL Entry` only for narrow audits. |

## Financial Risk Gate

Submitting or cancelling these accounting documents is treated as high-risk
financial work:

```text
Journal Entry
Payment Entry
Sales Invoice
Purchase Invoice
Period Closing Voucher
```

The adapter blocks `erpnext.submit_document`, `erpnext.cancel_document`, direct
`erpnext.call_method` calls to `agent_bridge.api.submit_document` /
`agent_bridge.api.cancel_document`, and generic create/update/delete or mutating
`frappe.client.*` calls for accounting structure DocTypes unless arguments include:

```json
{
  "confirmation": {
    "confirmed_by": "finance.user@example.com",
    "confirmed_at": "2026-06-09T10:00:00Z",
    "confirmation_text": "确认提交付款 ACC-PAY-0001",
    "reason": "User explicitly approved submitting Payment Entry ACC-PAY-0001."
  }
}
```

Blocked calls return:

```text
error_type = financial_confirmation_required
meta.risk_level = L5_FINANCIAL
```

The first safe workflow is therefore:

```text
read report / inspect source docs
  -> create draft
  -> user or supervisor reviews draft in ERPNext
  -> submit only with explicit confirmation metadata
```

Preferred submit tool:

```json
{
  "tool": "erpnext.accounting.submit_financial_document",
  "arguments": {
    "doctype": "Payment Entry",
    "name": "ACC-PAY-0001",
    "confirmation": {
      "confirmed_by": "finance.user@example.com",
      "confirmed_at": "2026-06-09T10:00:00Z",
      "confirmation_text": "确认提交付款 ACC-PAY-0001",
      "reason": "Reviewed amount, party, bank account, references, and posting date."
    }
  }
}
```

Module tools return stable `ToolResult.data` shapes. Draft and submit tools
return:

```json
{
  "doctype": "Payment Entry",
  "name": "ACC-PAY-0001",
  "docstatus": 0,
  "status": "Draft",
  "summary": "Created Payment Entry draft.",
  "next_actions": ["review_payment_allocation", "confirm_submit"],
  "risk": {
    "level": "L3",
    "requires_confirmation_for_submit": true
  }
}
```

Read/report tools return records or rows with `summary`, `next_actions`, and
`risk.level = L0`; raw ERPNext payloads are kept in `ToolResult.debug`.

## Core DocType Coverage

| DocType / Capability | Status | Tooling |
| --- | --- | --- |
| `Company` | Read supported | Generic search/get. |
| `Account` | Read supported | `erpnext.accounting.search_accounts`. |
| `Cost Center` | Read supported | `erpnext.accounting.search_cost_centers`. |
| `Journal Entry` | Draft create supported; submit guarded | `create_journal_entry_draft`, `submit_financial_document`. |
| `Payment Entry` | Draft create supported; submit guarded | `create_payment_entry_draft`, `submit_financial_document`. |
| `Sales Invoice` | Draft create supported; submit guarded | `create_sales_invoice_draft`, `submit_financial_document`. |
| `Purchase Invoice` | Draft create supported; submit guarded | `create_purchase_invoice_draft`, `submit_financial_document`. |
| `GL Entry` | Read supported through report | Prefer `general_ledger`; generic search for narrow row audit. |
| Accounts Receivable | Read supported | `erpnext.accounting.accounts_receivable`. |
| Accounts Payable | Read supported | `erpnext.accounting.accounts_payable`. |
| `Bank Account` | Read supported | Generic search/get. |
| Bank Reconciliation | Preparation and confirmed matching supported | `prepare_bank_reconciliation`, `apply_bank_reconciliation`; new payment/journal posting remains draft-first through Accounting tools. |
| Tax Templates | Read and preparation supported | `search_tax_templates`, `prepare_invoice_taxes`. |
| `Budget` | Read and draft create/update supported | `search_budgets`, `create_budget_draft`, `update_budget_draft`. |
| `Fiscal Year` | Read supported | `search_fiscal_years`. |
| `Accounting Period` | Read supported | `search_accounting_periods`. |
| Payment terms | Read supported | `search_payment_terms`. |
| `Period Closing Voucher` | Draft create supported; submit guarded | `create_period_closing_voucher_draft`, `submit_financial_document`. |

## Remaining Gaps

- Bank reconciliation new-payment/new-journal posting wrapper. Current confirmed wrapper only matches existing ERPNext payment documents to a Bank Transaction.
- Full ERPNext server-side tax/charge recalculation before insert. Current tool prepares template rows and estimates simple percentage taxes; ERPNext still validates final invoice draft.
- Budget submit/cancel policy. Current tools only create/update draft budgets.
- Version-specific report filter validation beyond the local `get_report_filters` contract and basic ISO `from_date` / `to_date` range checks.
- Role-aware approval policy beyond the adapter-level confirmation metadata.

## Test Method

Unit tests:

```powershell
pytest tests/test_accounting_tools.py tests/test_erpnext_adapter.py
```

Optional local integration smoke, when `NEXTERP_LOCAL_*` credentials are set:

```powershell
pytest -m integration tests/test_erpnext_integration.py
```

Manual read-only smoke examples:

```json
{"tool": "erpnext.accounting.general_ledger", "arguments": {"company": "Your Company", "from_date": "2026-01-01", "to_date": "2026-12-31"}}
{"tool": "erpnext.accounting.get_report_filters", "arguments": {"report_name": "General Ledger"}}
{"tool": "erpnext.accounting.accounts_receivable", "arguments": {"company": "Your Company"}}
{"tool": "erpnext.accounting.search_accounts", "arguments": {"company": "Your Company", "limit": 20}}
```
