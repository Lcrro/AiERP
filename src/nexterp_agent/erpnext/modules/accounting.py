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

    def _accounting_create_purchase_invoice_from_purchase_receipt_draft(self, args: dict[str, Any]) -> ToolResult:
        purchase_receipt = args["purchase_receipt"]
        result = self.client.get_document("Purchase Receipt", purchase_receipt)
        if not result.ok:
            return result
        doc = result.data if isinstance(result.data, dict) else {}
        guard = _validate_purchase_receipt_for_purchase_invoice(doc, purchase_receipt)
        if guard:
            return guard

        context = _purchase_receipt_invoice_context(doc, args)
        errors = context["errors"]
        items = context["items"]
        if errors or not items:
            return ToolResult(
                ok=False,
                error="Purchase Invoice draft cannot be created from the current Purchase Receipt context.",
                error_type="validation_error",
                user_message="无法从该采购收货单创建采购发票草稿：请检查收货单状态、明细和可开票数量。",
                data={
                    "doctype": "Purchase Receipt",
                    "name": purchase_receipt,
                    "status": "Purchase Invoice Draft Blocked",
                    "summary": "Review Purchase Receipt context before creating a Purchase Invoice draft.",
                    "errors": errors,
                    "warnings": context["warnings"],
                    "next_actions": ["review_purchase_receipt", "retry_with_valid_rows"],
                    "risk": {"level": "L1", "requires_confirmation_for_submit": False},
                },
                debug={"raw_purchase_receipt": doc},
            )

        data = _without_empty(
            {
                "doctype": "Purchase Invoice",
                "supplier": doc.get("supplier"),
                "company": args.get("company") or doc.get("company"),
                "posting_date": args.get("posting_date"),
                "bill_no": args.get("bill_no"),
                "bill_date": args.get("bill_date"),
                "currency": doc.get("currency"),
                "project": doc.get("project"),
                "cost_center": doc.get("cost_center"),
                "items": items,
                "docstatus": 0,
            }
        )
        draft_result = _module_doc_result(
            self.client.create_document("Purchase Invoice", data),
            "Purchase Invoice",
            "L3",
            f"Created Purchase Invoice draft from Purchase Receipt {purchase_receipt} with {len(items)} item row(s).",
            ["review_taxes_and_totals", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )
        if draft_result.ok and isinstance(draft_result.data, dict):
            draft_result.data["source_purchase_receipt"] = purchase_receipt
            draft_result.data["source_item_count"] = len(items)
            draft_result.data["warnings"] = context["warnings"]
        if draft_result.ok and isinstance(draft_result.debug, dict):
            draft_result.debug["purchase_receipt_context"] = context
        return draft_result

    def _accounting_create_supplier_payment_from_purchase_invoice_draft(self, args: dict[str, Any]) -> ToolResult:
        purchase_invoice = args["purchase_invoice"]
        invoice_result = self.client.get_document("Purchase Invoice", purchase_invoice)
        if not invoice_result.ok:
            return invoice_result
        invoice = invoice_result.data if isinstance(invoice_result.data, dict) else {}
        if int(invoice.get("docstatus") or 0) != 1:
            return ToolResult(
                ok=False,
                error=f"Purchase Invoice {purchase_invoice} is not submitted.",
                error_type="validation_error",
                user_message="只有已提交的采购发票才能生成付款草稿。",
            )
        outstanding = _float_or_none(invoice.get("outstanding_amount")) or 0.0
        if outstanding <= 0:
            return ToolResult(
                ok=False,
                error=f"Purchase Invoice {purchase_invoice} has no outstanding amount.",
                error_type="validation_error",
                user_message="该采购发票没有未付金额，无需创建付款草稿。",
            )
        paid_amount = _float_or_none(args.get("paid_amount"))
        if paid_amount is not None and (paid_amount <= 0 or paid_amount > outstanding):
            return ToolResult(
                ok=False,
                error="Paid amount must be positive and cannot exceed invoice outstanding amount.",
                error_type="validation_error",
                user_message=f"付款金额必须大于0且不能超过未付金额 {outstanding:g}。",
            )
        method_args = {
            "dt": "Purchase Invoice",
            "dn": purchase_invoice,
        }
        if paid_amount is not None:
            method_args["party_amount"] = paid_amount
        if args.get("bank_account"):
            method_args["bank_account"] = args["bank_account"]
        generated = self.client.call_method(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            method_args,
        )
        if not generated.ok:
            return generated
        data = dict(generated.data) if isinstance(generated.data, dict) else {}
        if not data:
            return ToolResult(
                ok=False,
                error="ERPNext returned an empty Payment Entry draft.",
                error_type="validation_error",
                user_message="ERPNext 未能生成付款草稿，请检查发票、账户和公司默认配置。",
            )
        data.pop("name", None)
        data["doctype"] = "Payment Entry"
        data["docstatus"] = 0
        if args.get("posting_date"):
            data["posting_date"] = args["posting_date"]
        if args.get("reference_no"):
            data["reference_no"] = args["reference_no"]
        if args.get("reference_date"):
            data["reference_date"] = args["reference_date"]
        if args.get("remarks"):
            data["remarks"] = args["remarks"]
        draft = _module_doc_result(
            self.client.create_document("Payment Entry", data),
            "Payment Entry",
            "L3",
            f"Created supplier Payment Entry draft from Purchase Invoice {purchase_invoice}.",
            ["review_payment_accounts", "review_allocation", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )
        if draft.ok and isinstance(draft.data, dict):
            draft.data["source_purchase_invoice"] = purchase_invoice
            draft.data["outstanding_before_payment"] = outstanding
        return draft

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

    def _accounting_cancel_financial_document(self, args: dict[str, Any]) -> ToolResult:
        doctype = args["doctype"]
        if doctype not in ACCOUNTING_SUBMITTABLE_DOCTYPES:
            return ToolResult(
                ok=False,
                error=f"Unsupported financial cancel DocType: {doctype}",
                error_type="validation_error",
                user_message="此财务取消工具只支持日记账、付款、销售发票、采购发票和期末结转单。",
            )
        guard = _require_financial_confirmation(doctype, args.get("confirmation"))
        if guard:
            return guard
        current = self.client.get_document(doctype, args["name"])
        if not current.ok:
            return current
        document = current.data if isinstance(current.data, dict) else {}
        if int(document.get("docstatus") or 0) != 1:
            return ToolResult(
                ok=False,
                error=f"{doctype} {args['name']} is not submitted.",
                error_type="validation_error",
                user_message="只有已提交的财务单据才能执行取消冲销。",
            )
        return _module_doc_result(
            self.client.cancel_document(doctype, args["name"]),
            doctype,
            "L5_FINANCIAL",
            f"Cancelled {doctype}; ERPNext applied its standard reversal.",
            ["audit_reversal", "review_gl_impact"],
            requires_confirmation_for_submit=True,
        )


def _validate_purchase_receipt_for_purchase_invoice(doc: dict[str, Any], purchase_receipt: str) -> ToolResult | None:
    if doc.get("docstatus") != 1:
        return ToolResult(
            ok=False,
            error=f"Purchase Receipt {purchase_receipt} is not submitted.",
            error_type="validation_error",
            user_message="只有已提交的采购收货单才能生成采购发票草稿。",
            data={
                "doctype": "Purchase Receipt",
                "name": purchase_receipt,
                "docstatus": doc.get("docstatus"),
                "status": "Not Submitted",
                "summary": "Submit the Purchase Receipt before creating a Purchase Invoice from it.",
                "next_actions": ["submit_purchase_receipt", "retry_purchase_invoice_creation"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    if _truthy(doc.get("is_return")):
        return ToolResult(
            ok=False,
            error=f"Purchase Receipt {purchase_receipt} is a return document.",
            error_type="validation_error",
            user_message="退货收货单不能通过这个工具直接生成普通采购发票草稿。",
            data={
                "doctype": "Purchase Receipt",
                "name": purchase_receipt,
                "status": "Return Receipt Unsupported",
                "summary": "Use normal submitted Purchase Receipts for Purchase Invoice creation.",
                "next_actions": ["choose_original_purchase_receipt"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    return None


def _purchase_receipt_invoice_context(doc: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    source_rows = [row for row in doc.get("items") or [] if isinstance(row, dict)]
    requests = [row for row in args.get("selected_items") or [] if isinstance(row, dict)]
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    if requests:
        selected_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for request in requests:
            matches = _match_purchase_receipt_invoice_rows(source_rows, request)
            if not matches:
                errors.append({"type": "row_not_found", "request": request, "message": "No Purchase Receipt item row matched this request."})
                continue
            if len(matches) > 1:
                errors.append({"type": "ambiguous_row", "request": request, "message": "Multiple Purchase Receipt rows matched; provide purchase_receipt_item."})
                continue
            selected_rows.append((matches[0], request))
    else:
        selected_rows = [(row, {}) for row in source_rows]

    remaining_by_row: dict[str, float] = {}
    for index, (row, request) in enumerate(selected_rows):
        row_key = str(row.get("name") or f"row-{index}")
        billable_qty = remaining_by_row.setdefault(row_key, _purchase_receipt_billable_qty(row))
        if billable_qty <= 0:
            warnings.append(
                {
                    "type": "fully_billed_row_skipped",
                    "purchase_receipt_item": row.get("name"),
                    "item_code": row.get("item_code"),
                    "message": "Purchase Receipt row has no remaining quantity to bill.",
                }
            )
            continue
        requested_qty = _float_or_none(request.get("qty")) if request else None
        invoice_qty = requested_qty if requested_qty is not None else billable_qty
        if invoice_qty <= 0:
            errors.append({"type": "invalid_qty", "request": request, "message": "Requested Purchase Invoice quantity must be greater than zero."})
            continue
        if invoice_qty > billable_qty:
            errors.append(
                {
                    "type": "qty_exceeds_billable",
                    "purchase_receipt_item": row.get("name"),
                    "item_code": row.get("item_code"),
                    "requested_qty": invoice_qty,
                    "billable_qty": billable_qty,
                }
            )
            continue
        if not row.get("item_code"):
            errors.append({"type": "missing_item_code", "purchase_receipt_item": row.get("name"), "message": "Purchase Receipt row has no item_code."})
            continue
        items.append(_purchase_invoice_item_from_purchase_receipt_row(row, request, invoice_qty, doc))
        remaining_by_row[row_key] = billable_qty - invoice_qty

    return {
        "purchase_receipt": doc.get("name"),
        "items": items,
        "warnings": warnings,
        "errors": errors,
        "source_row_count": len(source_rows),
        "selected_row_count": len(selected_rows),
    }


def _match_purchase_receipt_invoice_rows(rows: list[dict[str, Any]], request: dict[str, Any]) -> list[dict[str, Any]]:
    if request.get("purchase_receipt_item"):
        return [row for row in rows if row.get("name") == request["purchase_receipt_item"]]
    if request.get("item_code"):
        return [row for row in rows if row.get("item_code") == request["item_code"]]
    return []


def _purchase_receipt_billable_qty(row: dict[str, Any]) -> float:
    qty = _float_or_none(row.get("qty")) or _float_or_none(row.get("received_qty")) or 0.0
    returned_qty = _float_or_none(row.get("returned_qty")) or 0.0
    billed_qty = _float_or_none(row.get("billed_qty"))
    if billed_qty is None:
        billed_amt = _float_or_none(row.get("billed_amt"))
        rate = _float_or_none(row.get("rate")) or _float_or_none(row.get("net_rate")) or 0.0
        billed_qty = (billed_amt / rate) if billed_amt is not None and rate > 0 else 0.0
    return max(qty - returned_qty - billed_qty, 0.0)


def _purchase_invoice_item_from_purchase_receipt_row(
    row: dict[str, Any],
    request: dict[str, Any],
    qty: float,
    doc: dict[str, Any],
) -> dict[str, Any]:
    rate = request.get("rate") if request.get("rate") is not None else row.get("rate")
    return _without_empty(
        {
            "item_code": row.get("item_code"),
            "qty": qty,
            "received_qty": qty,
            "uom": row.get("uom") or row.get("stock_uom"),
            "conversion_factor": row.get("conversion_factor"),
            "rate": rate,
            "price_list_rate": row.get("price_list_rate"),
            "warehouse": row.get("warehouse"),
            "expense_account": row.get("expense_account"),
            "cost_center": row.get("cost_center") or doc.get("cost_center"),
            "project": row.get("project") or doc.get("project"),
            "description": row.get("description"),
            "purchase_receipt": doc.get("name"),
            "pr_detail": row.get("name"),
            "purchase_order": row.get("purchase_order"),
            "po_detail": row.get("purchase_order_item"),
        }
    )
