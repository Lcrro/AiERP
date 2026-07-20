from __future__ import annotations

from .common import (
    BUYING_ITEM_LINE_SCHEMA,
    CONFIRMATION_SCHEMA,
    PICK_LIST_LOCATION_SCHEMA,
    STOCK_ENTRY_ITEM_SCHEMA,
    STOCK_PREVIEW_ITEM_SCHEMA,
    STOCK_RECONCILIATION_ITEM_SCHEMA,
    _object_schema,
)

ACCOUNTING_TOOL_SCHEMAS = [
    {
        "name": "erpnext.accounting.search_accounts",
        "description": "Read-only search for ERPNext Account rows by company, account type, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "account_type": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_cost_centers",
        "description": "Read-only search for ERPNext Cost Center rows by company, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_budgets",
        "description": "Read-only search for ERPNext Budget rows by company, fiscal year, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "fiscal_year": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_fiscal_years",
        "description": "Read-only search for ERPNext Fiscal Year records by year, disabled flag, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "year": {"type": "string"},
                "disabled": {"type": "boolean"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_accounting_periods",
        "description": "Read-only search for ERPNext Accounting Period records by company/date range, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_payment_terms",
        "description": "Read-only search for Payment Term or Payment Terms Template records.",
        "parameters": _object_schema(
            [],
            {
                "doctype": {"enum": ["Payment Term", "Payment Terms Template"]},
                "query": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_tax_templates",
        "description": "Read-only search for Sales or Purchase Taxes and Charges Template records.",
        "parameters": _object_schema(
            [],
            {
                "template_type": {"enum": ["sales", "purchase", "Sales Invoice", "Purchase Invoice"]},
                "query": {"type": "string"},
                "company": {"type": "string"},
                "tax_category": {"type": "string"},
                "disabled": {"type": "boolean"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.get_report_filters",
        "description": "Read-only accounting helper. Return the supported filter contract for a standard accounting report without running the report.",
        "parameters": _object_schema(
            ["report_name"],
            {
                "report_name": {
                    "enum": [
                        "General Ledger",
                        "Accounts Receivable",
                        "Accounts Payable",
                        "Trial Balance",
                        "Balance Sheet",
                        "Profit and Loss Statement",
                        "Cash Flow",
                    ]
                }
            },
        ),
    },
    {
        "name": "erpnext.accounting.general_ledger",
        "description": "Run ERPNext General Ledger as a read-only normalized report.",
        "parameters": _object_schema([], {"company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "account": {"type": "string"}, "party_type": {"type": "string"}, "party": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.accounts_receivable",
        "description": "Run ERPNext Accounts Receivable as a read-only normalized report.",
        "parameters": _object_schema([], {"company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "party": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.accounts_payable",
        "description": "Run ERPNext Accounts Payable as a read-only normalized report.",
        "parameters": _object_schema([], {"company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "party": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.financial_report",
        "description": "Run an allowed read-only ERPNext financial report: Trial Balance, Balance Sheet, Profit and Loss Statement, or Cash Flow.",
        "parameters": _object_schema(["report_name"], {"report_name": {"enum": ["Trial Balance", "Balance Sheet", "Profit and Loss Statement", "Cash Flow"]}, "company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "fiscal_year": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_journal_entry_draft",
        "description": "Create a Journal Entry draft only. Submitting the voucher is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_payment_entry_draft",
        "description": "Create a Payment Entry draft only. Submitting the payment is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_sales_invoice_draft",
        "description": "Create a Sales Invoice draft only. Submitting the invoice is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_purchase_invoice_draft",
        "description": "Create a Purchase Invoice draft only. Submitting the invoice is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
        "description": "Create a Purchase Invoice draft from a submitted Purchase Receipt while preserving source row references and checking billable quantity.",
        "parameters": _object_schema(
            ["purchase_receipt"],
            {
                "purchase_receipt": {"type": "string"},
                "posting_date": {"type": "string"},
                "bill_no": {"type": "string"},
                "bill_date": {"type": "string"},
                "company": {"type": "string"},
                "selected_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "purchase_receipt_item": {"type": "string"},
                            "item_code": {"type": "string"},
                            "qty": {"type": "number", "exclusiveMinimum": 0},
                            "rate": {"type": "number", "minimum": 0},
                        },
                    },
                },
            },
        ),
    },
    {
        "name": "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft",
        "description": "Create a Payment Entry draft from one submitted Purchase Invoice using ERPNext account defaults and invoice references. Does not submit payment.",
        "parameters": _object_schema(
            ["purchase_invoice"],
            {
                "purchase_invoice": {"type": "string"},
                "posting_date": {"type": "string"},
                "paid_amount": {"type": "number", "exclusiveMinimum": 0},
                "bank_account": {"type": "string"},
                "reference_no": {"type": "string"},
                "reference_date": {"type": "string"},
                "remarks": {"type": "string", "maxLength": 500},
            },
        ),
    },
    {
        "name": "erpnext.accounting.create_period_closing_voucher_draft",
        "description": "Create a Period Closing Voucher draft only. Submitting period close is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.prepare_payment_allocation",
        "description": "L1 read-only helper. Prepare Payment Entry reference allocations for submitted Sales/Purchase Invoices without creating or submitting payment.",
        "parameters": _object_schema(
            ["party_type", "party"],
            {
                "party_type": {"enum": ["Customer", "Supplier"]},
                "party": {"type": "string"},
                "payment_type": {"enum": ["Receive", "Pay"]},
                "invoice_doctype": {"enum": ["Sales Invoice", "Purchase Invoice"]},
                "invoice_names": {"type": "array", "items": {"type": "string"}},
                "company": {"type": "string"},
                "paid_amount": {"type": "number", "minimum": 0},
                "allocations": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.prepare_invoice_taxes",
        "description": "L1 helper. Prepare invoice tax rows from a Sales/Purchase tax template or explicit tax rows; ERPNext still validates final totals on draft creation.",
        "parameters": _object_schema(
            ["invoice_type"],
            {
                "invoice_type": {"enum": ["sales", "purchase", "Sales Invoice", "Purchase Invoice"]},
                "taxes_and_charges": {"type": "string"},
                "items": {"type": "array", "items": {"type": "object"}},
                "taxes": {"type": "array", "items": {"type": "object"}},
                "net_total": {"type": "number", "minimum": 0},
            },
        ),
    },
    {
        "name": "erpnext.accounting.prepare_bank_reconciliation",
        "description": "L1 read-only helper. Gather Bank Transaction and Payment Entry candidates for reconciliation review without matching or posting.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "bank_account": {"type": "string"},
                "status": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.apply_bank_reconciliation",
        "description": "L5_FINANCIAL. Match existing ERPNext payment documents to one Bank Transaction through agent_bridge after explicit finance confirmation. Does not create new payments or journal entries.",
        "parameters": _object_schema(
            ["bank_transaction", "matches", "confirmation"],
            {
                "bank_transaction": {"type": "string"},
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["payment_document", "payment_entry", "allocated_amount"],
                        "properties": {
                            "payment_document": {"type": "string"},
                            "payment_entry": {"type": "string"},
                            "allocated_amount": {"type": "number", "exclusiveMinimum": 0},
                        },
                    },
                },
                "replace_existing": {"type": "boolean"},
                "remarks": {"type": "string"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
    {
        "name": "erpnext.accounting.create_budget_draft",
        "description": "Create a Budget draft with docstatus forced to 0. Budget submission, if used, remains a separate reviewed action.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.update_budget_draft",
        "description": "Update a Budget draft with docstatus forced to 0. Does not submit budget controls.",
        "parameters": _object_schema(["name", "data"], {"name": {"type": "string"}, "data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.submit_financial_document",
        "description": "L5_FINANCIAL. Submit a GL-impacting financial document only after explicit confirmation metadata is present.",
        "parameters": _object_schema(
            ["doctype", "name", "confirmation"],
            {
                "doctype": {"enum": ["Journal Entry", "Payment Entry", "Sales Invoice", "Purchase Invoice", "Period Closing Voucher"]},
                "name": {"type": "string"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
    {
        "name": "erpnext.accounting.cancel_financial_document",
        "description": "L5_FINANCIAL. Cancel a submitted financial document so ERPNext performs its standard ledger reversal, after explicit finance confirmation.",
        "parameters": _object_schema(
            ["doctype", "name", "confirmation"],
            {
                "doctype": {"enum": ["Journal Entry", "Payment Entry", "Sales Invoice", "Purchase Invoice", "Period Closing Voucher"]},
                "name": {"type": "string"},
                "reason": {"type": "string", "maxLength": 500},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
]
