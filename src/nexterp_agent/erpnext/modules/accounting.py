from __future__ import annotations

from typing import Any

from ..schemas import ToolResult
from .common import *

class AccountingToolsMixin:
    def _accounting_search_accounts(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("company"):
            filters["company"] = args["company"]
        if args.get("account_type"):
            filters["account_type"] = args["account_type"]
        result = self.client.search_documents(
            "Account",
            filters=filters or None,
            fields=args.get("fields")
            or ["name", "account_name", "company", "parent_account", "root_type", "account_type", "is_group"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "lft asc"),
        )
        return _module_search_result(result, "Account", filters, "L0")

    def _accounting_search_cost_centers(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("company"):
            filters["company"] = args["company"]
        result = self.client.search_documents(
            "Cost Center",
            filters=filters or None,
            fields=args.get("fields") or ["name", "cost_center_name", "company", "parent_cost_center", "is_group"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "lft asc"),
        )
        return _module_search_result(result, "Cost Center", filters, "L0")

    def _accounting_search_budgets(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("company"):
            filters["company"] = args["company"]
        if args.get("fiscal_year"):
            filters["fiscal_year"] = args["fiscal_year"]
        result = self.client.search_documents(
            "Budget",
            filters=filters or None,
            fields=args.get("fields") or ["name", "company", "budget_against", "fiscal_year", "docstatus"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )
        return _module_search_result(result, "Budget", filters, "L0")

    def _accounting_search_fiscal_years(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("year"):
            filters["year"] = args["year"]
        if args.get("disabled") is not None:
            filters["disabled"] = args["disabled"]
        result = self.client.search_documents(
            "Fiscal Year",
            filters=filters or None,
            fields=args.get("fields") or ["name", "year", "year_start_date", "year_end_date", "disabled"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "year_start_date desc"),
        )
        return _module_search_result(result, "Fiscal Year", filters, "L0")

    def _accounting_search_accounting_periods(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("company"):
            filters["company"] = args["company"]
        if args.get("from_date"):
            filters["end_date"] = [">=", args["from_date"]]
        if args.get("to_date"):
            filters["start_date"] = ["<=", args["to_date"]]
        result = self.client.search_documents(
            "Accounting Period",
            filters=filters or None,
            fields=args.get("fields") or ["name", "company", "start_date", "end_date"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "start_date desc"),
        )
        return _module_search_result(result, "Accounting Period", filters, "L0")

    def _accounting_search_payment_terms(self, args: dict[str, Any]) -> ToolResult:
        doctype = args.get("doctype") or "Payment Term"
        if doctype not in {"Payment Term", "Payment Terms Template"}:
            return ToolResult(
                ok=False,
                error=f"Unsupported payment terms DocType: {doctype}",
                error_type="validation_error",
                user_message="付款条件查询只支持 Payment Term 或 Payment Terms Template。",
            )
        filters = dict(args.get("filters") or {})
        if args.get("query"):
            search_field = "payment_term_name" if doctype == "Payment Term" else "template_name"
            filters[search_field] = ["like", f"%{args['query']}%"]
        default_fields = (
            ["name", "payment_term_name", "due_date_based_on", "credit_days", "credit_months", "invoice_portion"]
            if doctype == "Payment Term"
            else ["name", "template_name", "allocate_payment_based_on_payment_terms"]
        )
        result = self.client.search_documents(
            doctype,
            filters=filters or None,
            fields=args.get("fields") or default_fields,
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )
        return _module_search_result(result, doctype, filters, "L0")

    def _accounting_search_tax_templates(self, args: dict[str, Any]) -> ToolResult:
        template_type = args.get("template_type") or "sales"
        template_doctype = _tax_template_doctype(template_type)
        if not template_doctype:
            return ToolResult(
                ok=False,
                error=f"Unsupported tax template type: {template_type}",
                error_type="validation_error",
                user_message="税模板查询只支持 sales 或 purchase。",
            )
        filters = dict(args.get("filters") or {})
        if args.get("company"):
            filters["company"] = args["company"]
        if args.get("tax_category"):
            filters["tax_category"] = args["tax_category"]
        if args.get("disabled") is not None:
            filters["disabled"] = args["disabled"]
        if args.get("query"):
            filters["title"] = ["like", f"%{args['query']}%"]
        result = self.client.search_documents(
            template_doctype,
            filters=filters or None,
            fields=args.get("fields") or ["name", "title", "company", "tax_category", "disabled", "is_default"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )
        return _module_search_result(result, template_doctype, filters, "L0")

    def _accounting_get_report_filters(self, args: dict[str, Any]) -> ToolResult:
        report_name = args["report_name"]
        spec = _accounting_report_filter_spec(report_name)
        if spec is None:
            return ToolResult(
                ok=False,
                error=f"Unsupported accounting report: {report_name}",
                error_type="validation_error",
                user_message="此财务报表过滤器工具只支持已登记的标准会计报表。",
            )
        report = self.client.get_document("Report", report_name)
        if not report.ok:
            return report
        raw = report.data if isinstance(report.data, dict) else {}
        return ToolResult(
            ok=True,
            status_code=report.status_code,
            raw_status_code=report.raw_status_code,
            data={
                "doctype": "Report",
                "name": report_name,
                "status": "Read Only",
                "summary": f"Read filter contract for accounting report {report_name}.",
                "required_filters": spec["required_filters"],
                "optional_filters": spec["optional_filters"],
                "defaults": spec["defaults"],
                "known_date_filters": spec["known_date_filters"],
                "does_not_run_report": True,
                "next_actions": ["collect_required_filters", "run_report_after_filters_are_ready"],
                "risk": {"level": "L0", "runs_report": False},
            },
            debug={"raw_report": raw},
        )

    def _accounting_general_ledger(self, args: dict[str, Any]) -> ToolResult:
        filters = _report_filters(args)
        guard = _validate_accounting_report_filters("General Ledger", filters)
        if guard:
            return guard
        return _module_report_result(self.client.run_report("General Ledger", filters=filters), "General Ledger", filters)

    def _accounting_accounts_receivable(self, args: dict[str, Any]) -> ToolResult:
        filters = _report_filters(args)
        guard = _validate_accounting_report_filters("Accounts Receivable", filters)
        if guard:
            return guard
        return _module_report_result(self.client.run_report("Accounts Receivable", filters=filters), "Accounts Receivable", filters)

    def _accounting_accounts_payable(self, args: dict[str, Any]) -> ToolResult:
        filters = _report_filters(args)
        guard = _validate_accounting_report_filters("Accounts Payable", filters)
        if guard:
            return guard
        return _module_report_result(self.client.run_report("Accounts Payable", filters=filters), "Accounts Payable", filters)

    def _accounting_financial_report(self, args: dict[str, Any]) -> ToolResult:
        report_name = args["report_name"]
        allowed = {"Trial Balance", "Balance Sheet", "Profit and Loss Statement", "Cash Flow"}
        if report_name not in allowed:
            return ToolResult(
                ok=False,
                error=f"Unsupported accounting financial report: {report_name}",
                error_type="validation_error",
                user_message="只支持 Trial Balance、Balance Sheet、Profit and Loss Statement、Cash Flow 财务报表。",
            )
        filters = _report_filters(args)
        guard = _validate_accounting_report_filters(report_name, filters)
        if guard:
            return guard
        return _module_report_result(self.client.run_report(report_name, filters=filters), report_name, filters)

    def _accounting_create_journal_entry_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Journal Entry", args["data"])
        return _module_doc_result(
            self.client.create_document("Journal Entry", data),
            "Journal Entry",
            "L3",
            "Created Journal Entry draft.",
            ["review_voucher", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _accounting_create_payment_entry_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Payment Entry", args["data"])
        return _module_doc_result(
            self.client.create_document("Payment Entry", data),
            "Payment Entry",
            "L3",
            "Created Payment Entry draft.",
            ["review_payment_allocation", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _accounting_create_sales_invoice_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Sales Invoice", args["data"])
        return _module_doc_result(
            self.client.create_document("Sales Invoice", data),
            "Sales Invoice",
            "L3",
            "Created Sales Invoice draft.",
            ["review_taxes_and_totals", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _accounting_create_purchase_invoice_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Purchase Invoice", args["data"])
        return _module_doc_result(
            self.client.create_document("Purchase Invoice", data),
            "Purchase Invoice",
            "L3",
            "Created Purchase Invoice draft.",
            ["review_taxes_and_totals", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _accounting_create_period_closing_voucher_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Period Closing Voucher", args["data"])
        return _module_doc_result(
            self.client.create_document("Period Closing Voucher", data),
            "Period Closing Voucher",
            "L3",
            "Created Period Closing Voucher draft.",
            ["review_closing_accounts", "review_period", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _accounting_prepare_payment_allocation(self, args: dict[str, Any]) -> ToolResult:
        party_type = args["party_type"]
        party = args["party"]
        payment_type = args.get("payment_type") or ("Receive" if party_type == "Customer" else "Pay")
        invoice_doctype = args.get("invoice_doctype") or _invoice_doctype_for_payment(party_type, payment_type)
        invoice_names = args.get("invoice_names") or []
        paid_amount = args.get("paid_amount")
        allocations = args.get("allocations") or {}

        if invoice_doctype not in {"Sales Invoice", "Purchase Invoice"}:
            return ToolResult(
                ok=False,
                error=f"Unsupported invoice DocType for payment allocation: {invoice_doctype}",
                error_type="validation_error",
                user_message="付款分配目前只支持 Sales Invoice 和 Purchase Invoice。",
            )

        if invoice_names:
            invoices = []
            for name in invoice_names:
                result = self.client.get_document(invoice_doctype, name)
                if not result.ok:
                    return result
                if isinstance(result.data, dict):
                    invoices.append(result.data)
        else:
            filters: dict[str, Any] = {
                "docstatus": 1,
                "outstanding_amount": [">", 0],
            }
            if party_type == "Customer":
                filters["customer"] = party
            elif party_type == "Supplier":
                filters["supplier"] = party
            if args.get("company"):
                filters["company"] = args["company"]
            result = self.client.search_documents(
                invoice_doctype,
                filters=filters,
                fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency", "company"],
                limit=args.get("limit", 20),
                order_by=args.get("order_by", "due_date asc"),
            )
            if not result.ok:
                return result
            invoices = result.data if isinstance(result.data, list) else []

        references, unallocated = _payment_references(invoices, paid_amount, allocations, invoice_doctype)
        return ToolResult(
            ok=True,
            data={
                "status": "Prepared",
                "summary": f"Prepared payment allocation for {party_type} {party} across {len(references)} invoice(s).",
                "payment_type": payment_type,
                "party_type": party_type,
                "party": party,
                "paid_amount": paid_amount,
                "unallocated_amount": unallocated,
                "references": references,
                "next_actions": ["review_allocations", "create_payment_entry_draft"],
                "risk": {"level": "L1", "creates_financial_posting": False},
            },
            debug={"source_invoices": invoices},
        )

    def _accounting_prepare_invoice_taxes(self, args: dict[str, Any]) -> ToolResult:
        invoice_type = args["invoice_type"]
        template = args.get("taxes_and_charges")
        template_doctype = _tax_template_doctype(invoice_type)
        if not template_doctype:
            return ToolResult(
                ok=False,
                error=f"Unsupported invoice_type: {invoice_type}",
                error_type="validation_error",
                user_message="税费准备目前只支持 sales 或 purchase 发票。",
            )

        source_taxes = args.get("taxes") or []
        template_doc = None
        if template:
            result = self.client.get_document(template_doctype, template)
            if not result.ok:
                return result
            template_doc = result.data if isinstance(result.data, dict) else {}
            source_taxes = template_doc.get("taxes") or source_taxes

        net_total = args.get("net_total")
        if net_total is None:
            net_total = sum(float(row.get("amount") or row.get("net_amount") or 0) for row in args.get("items") or [])
        tax_rows, estimated_total_tax = _prepared_tax_rows(source_taxes, float(net_total or 0))
        return ToolResult(
            ok=True,
            data={
                "status": "Prepared",
                "summary": f"Prepared {len(tax_rows)} tax row(s) for {invoice_type} invoice.",
                "invoice_type": invoice_type,
                "taxes_and_charges": template,
                "net_total": net_total,
                "estimated_total_tax": estimated_total_tax,
                "taxes": tax_rows,
                "next_actions": ["review_tax_rows", "create_invoice_draft", "let_erpnext_validate_totals"],
                "risk": {"level": "L1", "creates_financial_posting": False},
            },
            debug={"template": template_doc, "source_taxes": source_taxes},
        )

    def _accounting_prepare_bank_reconciliation(self, args: dict[str, Any]) -> ToolResult:
        transaction_filters: dict[str, Any] = {}
        for key in ("bank_account", "company", "status"):
            if args.get(key):
                transaction_filters[key] = args[key]
        if args.get("from_date"):
            transaction_filters["date"] = [">=", args["from_date"]]
        if args.get("to_date"):
            transaction_filters["date"] = ["between", [args.get("from_date") or "1900-01-01", args["to_date"]]]

        transactions = self.client.search_documents(
            "Bank Transaction",
            filters=transaction_filters or None,
            fields=["name", "date", "bank_account", "deposit", "withdrawal", "currency", "description", "status"],
            limit=args.get("limit", 50),
            order_by=args.get("order_by", "date desc"),
        )
        if not transactions.ok:
            return transactions

        payment_filters: dict[str, Any] = {"docstatus": 1}
        for key in ("company", "bank_account"):
            if args.get(key):
                payment_filters[key] = args[key]
        if args.get("from_date"):
            payment_filters["posting_date"] = [">=", args["from_date"]]
        if args.get("to_date"):
            payment_filters["posting_date"] = ["between", [args.get("from_date") or "1900-01-01", args["to_date"]]]
        payments = self.client.search_documents(
            "Payment Entry",
            filters=payment_filters,
            fields=["name", "posting_date", "payment_type", "party_type", "party", "paid_amount", "received_amount", "reference_no"],
            limit=args.get("limit", 50),
            order_by="posting_date desc",
        )
        if not payments.ok:
            return payments

        bank_rows = transactions.data if isinstance(transactions.data, list) else []
        payment_rows = payments.data if isinstance(payments.data, list) else []
        return ToolResult(
            ok=True,
            data={
                "status": "Prepared",
                "summary": f"Prepared bank reconciliation review with {len(bank_rows)} bank transaction(s) and {len(payment_rows)} payment candidate(s).",
                "bank_account": args.get("bank_account"),
                "company": args.get("company"),
                "bank_transactions": bank_rows,
                "payment_candidates": payment_rows,
                "next_actions": ["review_matches", "use_erpnext_bank_reconciliation_ui_or_future_confirmed_wrapper"],
                "risk": {"level": "L1", "creates_financial_posting": False},
            },
            debug={"bank_transaction_filters": transaction_filters, "payment_filters": payment_filters},
        )

    def _accounting_apply_bank_reconciliation(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_l5_financial_confirmation(
            "bank_reconciliation",
            args.get("bank_transaction"),
            args.get("confirmation"),
        )
        if guard:
            return guard
        result = self.client.call_method(
            "agent_bridge.api.reconcile_bank_transaction",
            {
                "bank_transaction": args["bank_transaction"],
                "matches": args["matches"],
                "replace_existing": args.get("replace_existing", False),
                "remarks": args.get("remarks"),
            },
        )
        if not result.ok:
            return result
        raw = result.data if isinstance(result.data, dict) else {}
        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data={
                "doctype": "Bank Transaction",
                "name": raw.get("name") or args["bank_transaction"],
                "docstatus": raw.get("docstatus"),
                "status": raw.get("status") or "Reconciled",
                "summary": f"Applied bank reconciliation for Bank Transaction {raw.get('name') or args['bank_transaction']}.",
                "matched_count": raw.get("matched_count", len(args["matches"])),
                "allocated_amount": raw.get("allocated_amount"),
                "unallocated_amount": raw.get("unallocated_amount"),
                "next_actions": ["audit_bank_reconciliation", "review_bank_transaction"],
                "risk": {
                    "level": "L5_FINANCIAL",
                    "requires_confirmation_for_submit": False,
                    "confirmation_checked": True,
                },
            },
            debug={"raw_document": raw},
        )

    def _accounting_create_budget_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Budget", args["data"])
        return _module_doc_result(
            self.client.create_document("Budget", data),
            "Budget",
            "L3",
            "Created Budget draft.",
            ["review_budget_accounts", "confirm_submit_if_required"],
            requires_confirmation_for_submit=True,
        )

    def _accounting_update_budget_draft(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args["data"])
        data["docstatus"] = 0
        return _module_doc_result(
            self.client.update_document("Budget", args["name"], data),
            "Budget",
            "L3",
            "Updated Budget draft.",
            ["review_budget_accounts", "confirm_submit_if_required"],
            requires_confirmation_for_submit=True,
        )

    def _accounting_submit_financial_document(self, args: dict[str, Any]) -> ToolResult:
        doctype = args["doctype"]
        if doctype not in ACCOUNTING_SUBMITTABLE_DOCTYPES:
            return ToolResult(
                ok=False,
                error=f"Unsupported financial submit DocType: {doctype}",
                error_type="validation_error",
                user_message="此财务提交工具只支持 Journal Entry、Payment Entry、Sales Invoice、Purchase Invoice、Period Closing Voucher。",
            )
        guard = _require_financial_confirmation(doctype, args.get("confirmation"))
        if guard:
            return guard
        return _module_doc_result(
            self.client.submit_document(doctype, args["name"]),
            doctype,
            "L5_FINANCIAL",
            f"Submitted {doctype}.",
            ["audit_posting", "review_gl_impact"],
            requires_confirmation_for_submit=True,
        )
