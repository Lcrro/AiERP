from __future__ import annotations

from collections.abc import Callable
from datetime import date
import os
from time import perf_counter
from typing import Any

from nexterp_agent.item_master import MaterialSearch, PostgresCatalogSearchClient

from .client import ERPNextClient
from .schemas import ToolCall, ToolResult


ACCOUNTING_SUBMITTABLE_DOCTYPES = {
    "Journal Entry",
    "Payment Entry",
    "Sales Invoice",
    "Purchase Invoice",
    "Period Closing Voucher",
}

ACCOUNTING_STRUCTURE_DOCTYPES = {
    "Account",
    "Cost Center",
    "Bank Account",
    "Mode of Payment",
    "Fiscal Year",
    "Accounting Period",
    "Payment Term",
    "Payment Terms Template",
    "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
    "Tax Category",
    "Tax Rule",
    "Finance Book",
    "Budget",
}

ACCOUNTING_WRITE_GUARDED_DOCTYPES = ACCOUNTING_SUBMITTABLE_DOCTYPES | ACCOUNTING_STRUCTURE_DOCTYPES

ACCOUNTING_MUTATING_METHODS = {
    "frappe.client.insert",
    "frappe.client.save",
    "frappe.client.set_value",
    "frappe.client.delete",
    "frappe.client.submit",
    "frappe.client.cancel",
}

STOCK_SUBMITTABLE_DOCTYPES = {
    "Stock Entry",
    "Stock Reconciliation",
    "Delivery Note",
    "Purchase Receipt",
    "Purchase Invoice",
    "Sales Invoice",
    "Pick List",
    "Stock Reservation Entry",
}

ASSET_SUBMITTABLE_DOCTYPES = {
    "Asset",
    "Asset Movement",
    "Asset Maintenance",
    "Asset Maintenance Log",
    "Asset Repair",
    "Asset Value Adjustment",
}

ASSET_FINANCIAL_DOCTYPES = {
    "Asset",
    "Asset Value Adjustment",
}

BUYING_SUBMITTABLE_DOCTYPES = {
    "Material Request",
    "Request for Quotation",
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
}

USER_PERMISSION_ACTIONS = (
    "select",
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
)


class ERPNextAdapter:
    """Execute structured ToolCalls against ERPNext."""

    def __init__(self, client: ERPNextClient) -> None:
        self.client = client
        self.handlers: dict[str, Callable[[dict[str, Any]], ToolResult]] = {
            "erpnext.get_logged_user": self._get_logged_user,
            "erpnext.search_documents": self._search_documents,
            "erpnext.search_items": self._search_items,
            "erpnext.count_documents": self._count_documents,
            "erpnext.get_document": self._get_document,
            "erpnext.create_document": self._create_document,
            "erpnext.update_document": self._update_document,
            "erpnext.delete_document": self._delete_document,
            "erpnext.document_exists": self._document_exists,
            "erpnext.resolve_link": self._resolve_link,
            "erpnext.validate_fields": self._validate_fields,
            "erpnext.get_doctype_schema": self._get_doctype_schema,
            "erpnext.call_method": self._call_method,
            "erpnext.submit_document": self._submit_document,
            "erpnext.cancel_document": self._cancel_document,
            "erpnext.amend_document": self._amend_document,
            "erpnext.get_workflow_actions": self._get_workflow_actions,
            "erpnext.apply_workflow": self._apply_workflow,
            "erpnext.run_report": self._run_report,
            "erpnext.users.list_users": self._users_list_users,
            "erpnext.users.get_user_access_summary": self._users_get_user_access_summary,
            "erpnext.users.list_roles": self._users_list_roles,
            "erpnext.users.list_role_profiles": self._users_list_role_profiles,
            "erpnext.users.preview_role_profile_roles": self._users_preview_role_profile_roles,
            "erpnext.users.list_user_permissions": self._users_list_user_permissions,
            "erpnext.users.list_shared_documents": self._users_list_shared_documents,
            "erpnext.users.list_access_logs": self._users_list_access_logs,
            "erpnext.users.list_activity_logs": self._users_list_activity_logs,
            "erpnext.users.get_permission_metadata": self._users_get_permission_metadata,
            "erpnext.users.preview_effective_permissions": self._users_preview_effective_permissions,
            "erpnext.users.check_server_permission": self._users_check_server_permission,
            "erpnext.users.preview_permission_policy_change": self._users_preview_permission_policy_change,
            "erpnext.users.create_user_draft": self._users_create_user_draft,
            "erpnext.users.set_user_enabled": self._users_set_user_enabled,
            "erpnext.users.assign_roles": self._users_assign_roles,
            "erpnext.users.create_user_permission": self._users_create_user_permission,
            "erpnext.users.delete_user_permission": self._users_delete_user_permission,
            "erpnext.setup_item_master": self._setup_item_master,
            "erpnext.prepare_item_from_intent": self._prepare_item_from_intent,
            "erpnext.create_item_from_intent": self._create_item_from_intent,
            "erpnext.create_todo": self._create_todo,
            "erpnext.add_comment": self._add_comment,
            "erpnext.get_comments": self._get_comments,
            "erpnext.assign_to": self._assign_to,
            "erpnext.clear_assignment": self._clear_assignment,
            "erpnext.attach_file": self._attach_file,
            "erpnext.list_attachments": self._list_attachments,
            "erpnext.delete_attachment": self._delete_attachment,
            "erpnext.buying.search_suppliers": self._buying_search_suppliers,
            "erpnext.buying.search_supplier_scorecards": self._buying_search_supplier_scorecards,
            "erpnext.buying.get_supplier_procurement_profile": self._buying_get_supplier_procurement_profile,
            "erpnext.buying.create_supplier_group_draft": self._buying_create_supplier_group_draft,
            "erpnext.buying.create_supplier_draft": self._buying_create_supplier_draft,
            "erpnext.buying.create_material_request_draft": self._buying_create_material_request_draft,
            "erpnext.buying.create_request_for_quotation_draft": self._buying_create_request_for_quotation_draft,
            "erpnext.buying.create_supplier_quotation_draft": self._buying_create_supplier_quotation_draft,
            "erpnext.buying.compare_supplier_quotations": self._buying_compare_supplier_quotations,
            "erpnext.buying.create_purchase_order_draft": self._buying_create_purchase_order_draft,
            "erpnext.buying.create_purchase_receipt_draft": self._buying_create_purchase_receipt_draft,
            "erpnext.buying.generate_purchase_suggestions": self._buying_generate_purchase_suggestions,
            "erpnext.buying.search_item_suppliers": self._buying_search_item_suppliers,
            "erpnext.buying.search_item_prices": self._buying_search_item_prices,
            "erpnext.buying.get_buying_settings": self._buying_get_buying_settings,
            "erpnext.buying.run_purchase_analysis": self._buying_run_purchase_analysis,
            "erpnext.buying.submit_document": self._buying_submit_document,
            "erpnext.accounting.search_accounts": self._accounting_search_accounts,
            "erpnext.accounting.search_cost_centers": self._accounting_search_cost_centers,
            "erpnext.accounting.search_budgets": self._accounting_search_budgets,
            "erpnext.accounting.search_fiscal_years": self._accounting_search_fiscal_years,
            "erpnext.accounting.search_accounting_periods": self._accounting_search_accounting_periods,
            "erpnext.accounting.search_payment_terms": self._accounting_search_payment_terms,
            "erpnext.accounting.search_tax_templates": self._accounting_search_tax_templates,
            "erpnext.accounting.get_report_filters": self._accounting_get_report_filters,
            "erpnext.accounting.general_ledger": self._accounting_general_ledger,
            "erpnext.accounting.accounts_receivable": self._accounting_accounts_receivable,
            "erpnext.accounting.accounts_payable": self._accounting_accounts_payable,
            "erpnext.accounting.financial_report": self._accounting_financial_report,
            "erpnext.accounting.create_journal_entry_draft": self._accounting_create_journal_entry_draft,
            "erpnext.accounting.create_payment_entry_draft": self._accounting_create_payment_entry_draft,
            "erpnext.accounting.create_sales_invoice_draft": self._accounting_create_sales_invoice_draft,
            "erpnext.accounting.create_purchase_invoice_draft": self._accounting_create_purchase_invoice_draft,
            "erpnext.accounting.create_period_closing_voucher_draft": self._accounting_create_period_closing_voucher_draft,
            "erpnext.accounting.prepare_payment_allocation": self._accounting_prepare_payment_allocation,
            "erpnext.accounting.prepare_invoice_taxes": self._accounting_prepare_invoice_taxes,
            "erpnext.accounting.prepare_bank_reconciliation": self._accounting_prepare_bank_reconciliation,
            "erpnext.accounting.apply_bank_reconciliation": self._accounting_apply_bank_reconciliation,
            "erpnext.accounting.create_budget_draft": self._accounting_create_budget_draft,
            "erpnext.accounting.update_budget_draft": self._accounting_update_budget_draft,
            "erpnext.accounting.submit_financial_document": self._accounting_submit_financial_document,
            "erpnext.assets.search_assets": self._assets_search_assets,
            "erpnext.assets.search_asset_categories": self._assets_search_asset_categories,
            "erpnext.assets.search_asset_locations": self._assets_search_asset_locations,
            "erpnext.assets.get_financial_snapshot": self._assets_get_financial_snapshot,
            "erpnext.assets.get_depreciation_schedule": self._assets_get_depreciation_schedule,
            "erpnext.assets.create_asset_draft": self._assets_create_asset_draft,
            "erpnext.assets.create_movement_draft": self._assets_create_movement_draft,
            "erpnext.assets.create_maintenance_draft": self._assets_create_maintenance_draft,
            "erpnext.assets.create_maintenance_log_draft": self._assets_create_maintenance_log_draft,
            "erpnext.assets.create_repair_draft": self._assets_create_repair_draft,
            "erpnext.assets.create_value_adjustment_draft": self._assets_create_value_adjustment_draft,
            "erpnext.assets.prepare_disposal_or_sale": self._assets_prepare_disposal_or_sale,
            "erpnext.assets.submit_document": self._assets_submit_document,
            "erpnext.stock.get_balance": self._stock_get_balance,
            "erpnext.stock.get_item_locations": self._stock_get_item_locations,
            "erpnext.stock.get_ledger_entries": self._stock_get_ledger_entries,
            "erpnext.stock.get_stock_settings": self._stock_get_stock_settings,
            "erpnext.stock.resolve_item": self._stock_resolve_item,
            "erpnext.stock.create_entry_draft": self._stock_create_entry_draft,
            "erpnext.stock.create_reconciliation_draft": self._stock_create_reconciliation_draft,
            "erpnext.stock.search_batches": self._stock_search_batches,
            "erpnext.stock.list_batch_balances": self._stock_list_batch_balances,
            "erpnext.stock.search_serial_numbers": self._stock_search_serial_numbers,
            "erpnext.stock.create_batch": self._stock_create_batch,
            "erpnext.stock.update_batch": self._stock_update_batch,
            "erpnext.stock.create_serial_no": self._stock_create_serial_no,
            "erpnext.stock.update_serial_no": self._stock_update_serial_no,
            "erpnext.stock.list_pick_lists": self._stock_list_pick_lists,
            "erpnext.stock.create_pick_list_draft": self._stock_create_pick_list_draft,
            "erpnext.stock.list_reservations": self._stock_list_reservations,
            "erpnext.stock.create_reservation_draft": self._stock_create_reservation_draft,
            "erpnext.stock.preview_valuation": self._stock_preview_valuation,
            "erpnext.stock.allocate_shortages": self._stock_allocate_shortages,
            "erpnext.stock.list_delivery_notes": self._stock_list_delivery_notes,
            "erpnext.stock.list_purchase_receipts": self._stock_list_purchase_receipts,
            "erpnext.stock.get_document_impact": self._stock_get_document_impact,
            "erpnext.stock.list_item_reorders": self._stock_list_item_reorders,
            "erpnext.stock.list_quality_inspections": self._stock_list_quality_inspections,
            "erpnext.stock.list_warehouses": self._stock_list_warehouses,
            "erpnext.stock.create_warehouse": self._stock_create_warehouse,
            "erpnext.stock.update_warehouse": self._stock_update_warehouse,
            "erpnext.stock.list_item_groups": self._stock_list_item_groups,
            "erpnext.stock.create_item_group": self._stock_create_item_group,
            "erpnext.stock.update_item_group": self._stock_update_item_group,
            "erpnext.stock.list_uoms": self._stock_list_uoms,
            "erpnext.stock.create_uom": self._stock_create_uom,
            "erpnext.stock.update_uom": self._stock_update_uom,
            "erpnext.stock.submit_document": self._stock_submit_document,
        }

    def execute(self, tool_call: ToolCall | dict[str, Any]) -> ToolResult:
        started = perf_counter()
        call = ToolCall.from_dict(tool_call) if isinstance(tool_call, dict) else tool_call
        handler = self.handlers.get(call.tool)
        if handler is None:
            return self._finish(
                call,
                started,
                ToolResult(
                    ok=False,
                    error=f"Unsupported tool: {call.tool}",
                    error_type="unsupported_tool",
                    user_message=f"不支持的工具：{call.tool}",
                ),
            )

        try:
            return self._finish(call, started, handler(call.arguments))
        except KeyError as exc:
            return self._finish(
                call,
                started,
                ToolResult(
                    ok=False,
                    error=f"Missing required argument: {exc.args[0]}",
                    error_type="missing_argument",
                    user_message=f"工具调用缺少必要参数：{exc.args[0]}",
                ),
            )
        except TypeError as exc:
            return self._finish(
                call,
                started,
                ToolResult(
                    ok=False,
                    error=f"Invalid tool arguments: {exc}",
                    error_type="validation_error",
                    user_message="工具调用参数格式不正确。",
                ),
            )

    def _finish(self, call: ToolCall, started: float, result: ToolResult) -> ToolResult:
        return result.with_call(call, duration_ms=int((perf_counter() - started) * 1000))

    def _get_logged_user(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_logged_user()

    def _search_documents(self, args: dict[str, Any]) -> ToolResult:
        return self.client.search_documents(
            args["doctype"],
            filters=args.get("filters"),
            fields=args.get("fields"),
            limit=args.get("limit", 20),
            offset=args.get("offset", 0),
            order_by=args.get("order_by"),
        )

    def _search_items(self, args: dict[str, Any]) -> ToolResult:
        search = MaterialSearch(self.client)
        return ToolResult(
            ok=True,
            data=search.search_items(
                args["query"],
                specs=args.get("specs"),
                item_group=args.get("item_group"),
                enabled_only=args.get("enabled_only", True),
                limit=args.get("limit", 10),
            ),
        )

    def _count_documents(self, args: dict[str, Any]) -> ToolResult:
        return self.client.count_documents(args["doctype"], filters=args.get("filters"))

    def _get_document(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_document(args["doctype"], args["name"])

    def _create_document(self, args: dict[str, Any]) -> ToolResult:
        data = args.get("data") if isinstance(args.get("data"), dict) else {}
        guard = _require_accounting_write_confirmation(
            "generic_create_document",
            args["doctype"],
            data.get("name"),
            args.get("confirmation"),
        )
        if guard:
            return guard
        return self.client.create_document(args["doctype"], args["data"])

    def _update_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_accounting_write_confirmation(
            "generic_update_document",
            args["doctype"],
            args["name"],
            args.get("confirmation"),
        )
        if guard:
            return guard
        return self.client.update_document(args["doctype"], args["name"], args["data"])

    def _delete_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_accounting_write_confirmation(
            "generic_delete_document",
            args["doctype"],
            args["name"],
            args.get("confirmation"),
        )
        if guard:
            return guard
        return self.client.delete_document(args["doctype"], args["name"])

    def _document_exists(self, args: dict[str, Any]) -> ToolResult:
        return self.client.document_exists(args["doctype"], args["name"])

    def _resolve_link(self, args: dict[str, Any]) -> ToolResult:
        return self.client.resolve_link(
            args["doctype"],
            args["query"],
            search_field=args.get("search_field", "name"),
            limit=args.get("limit", 10),
        )

    def _validate_fields(self, args: dict[str, Any]) -> ToolResult:
        return self.client.validate_fields(args["doctype"], args["fields"])

    def _get_doctype_schema(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_doctype_schema(args["doctype"])

    def _call_method(self, args: dict[str, Any]) -> ToolResult:
        method_args = args.get("args") if isinstance(args.get("args"), dict) else {}
        guarded_doctype = _call_method_doctype(args["method"], method_args)
        if args["method"] in ACCOUNTING_MUTATING_METHODS:
            guard = _require_accounting_write_confirmation(
                args["method"],
                guarded_doctype,
                _call_method_name(method_args),
                args.get("confirmation"),
            )
            if guard:
                return guard
        if args["method"] in {"agent_bridge.api.submit_document", "agent_bridge.api.cancel_document"}:
            guard = _require_financial_confirmation(guarded_doctype, args.get("confirmation"))
            if guard:
                return guard
            stock_guard = _require_stock_confirmation(guarded_doctype, method_args.get("name"), args.get("confirmation"))
            if stock_guard:
                return stock_guard
            asset_guard = _require_asset_confirmation(guarded_doctype, method_args.get("name"), args.get("confirmation"))
            if asset_guard:
                return asset_guard
        return self.client.call_method(
            args["method"],
            args.get("args", {}),
            http_method=args.get("http_method", "POST"),
        )

    def _submit_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_financial_confirmation(args["doctype"], args.get("confirmation"))
        if guard:
            return guard
        stock_guard = _require_stock_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if stock_guard:
            return stock_guard
        asset_guard = _require_asset_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if asset_guard:
            return asset_guard
        return self.client.submit_document(args["doctype"], args["name"])

    def _cancel_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_financial_confirmation(args["doctype"], args.get("confirmation"))
        if guard:
            return guard
        stock_guard = _require_stock_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if stock_guard:
            return stock_guard
        asset_guard = _require_asset_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if asset_guard:
            return asset_guard
        return self.client.cancel_document(args["doctype"], args["name"])

    def _amend_document(self, args: dict[str, Any]) -> ToolResult:
        return self.client.amend_document(args["doctype"], args["name"])

    def _get_workflow_actions(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_workflow_actions(args["doctype"], args["name"])

    def _apply_workflow(self, args: dict[str, Any]) -> ToolResult:
        return self.client.apply_workflow(args["doctype"], args["name"], args["action"])

    def _run_report(self, args: dict[str, Any]) -> ToolResult:
        return self.client.run_report(
            args["report_name"],
            filters=args.get("filters"),
            ignore_prepared_report=args.get("ignore_prepared_report", True),
        )

    def _users_list_users(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("enabled", "user_type", "role_profile_name"))
        if args.get("query"):
            filters.append(["full_name", "like", f"%{args['query']}%"])
        result = self.client.search_documents(
            "User",
            filters=filters or None,
            fields=[
                "name",
                "email",
                "first_name",
                "last_name",
                "full_name",
                "enabled",
                "user_type",
                "role_profile_name",
                "last_login",
                "last_active",
                "modified",
            ],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "User", "Listed ERPNext users.")

    def _users_get_user_access_summary(self, args: dict[str, Any]) -> ToolResult:
        user = args["user"]
        doc = self.client.get_document("User", user)
        if not doc.ok:
            return doc
        data = doc.data if isinstance(doc.data, dict) else {}
        roles = [
            row.get("role")
            for row in data.get("roles", [])
            if isinstance(row, dict) and row.get("role")
        ]
        permissions = None
        if args.get("include_permissions", True):
            permissions_result = self.client.search_documents(
                "User Permission",
                filters={"user": user},
                fields=["name", "user", "allow", "for_value", "applicable_for", "is_default", "hide_descendants"],
                limit=100,
                order_by="modified desc",
            )
            if not permissions_result.ok:
                return permissions_result
            permissions = permissions_result.data
        return ToolResult(
            ok=True,
            status_code=doc.status_code,
            raw_status_code=doc.raw_status_code,
            data={
                "doctype": "User",
                "name": data.get("name") or user,
                "status": "Enabled" if data.get("enabled") else "Disabled",
                "summary": f"Access summary for {data.get('name') or user}.",
                "user": {
                    "email": data.get("email"),
                    "full_name": data.get("full_name"),
                    "enabled": data.get("enabled"),
                    "user_type": data.get("user_type"),
                    "role_profile_name": data.get("role_profile_name"),
                },
                "roles": roles,
                "user_permissions": permissions,
                "next_actions": ["review_roles", "review_user_permissions"],
                "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
            },
            debug={"raw_document": data},
        )

    def _users_list_roles(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("disabled", "desk_access"))
        if args.get("query"):
            filters.append(["role_name", "like", f"%{args['query']}%"])
        result = self.client.search_documents(
            "Role",
            filters=filters or None,
            fields=["name", "role_name", "desk_access", "disabled", "is_custom", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="role_name asc",
        )
        return _users_read_result(result, "Role", "Listed ERPNext roles.")

    def _users_list_role_profiles(self, args: dict[str, Any]) -> ToolResult:
        filters = []
        if args.get("query"):
            filters.append(["role_profile", "like", f"%{args['query']}%"])
        result = self.client.search_documents(
            "Role Profile",
            filters=filters or None,
            fields=["name", "role_profile", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "Role Profile", "Listed ERPNext role profiles.")

    def _users_preview_role_profile_roles(self, args: dict[str, Any]) -> ToolResult:
        role_profile = args["role_profile"]
        result = self.client.get_document("Role Profile", role_profile)
        if not result.ok:
            return result
        data = result.data if isinstance(result.data, dict) else {}
        role_rows = data.get("roles") or []
        roles = [
            row.get("role")
            for row in role_rows
            if isinstance(row, dict) and row.get("role")
        ]
        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data={
                "doctype": "Role Profile",
                "name": data.get("name") or role_profile,
                "status": "Preview",
                "summary": f"Role Profile {role_profile} expands to {len(roles)} role(s).",
                "role_profile": role_profile,
                "roles": roles,
                "role_count": len(roles),
                "next_actions": ["review_roles", "use_create_user_draft_or_assign_roles"],
                "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
            },
            debug={"raw_document": data},
        )

    def _users_list_user_permissions(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user", "allow", "for_value", "applicable_for"))
        result = self.client.search_documents(
            "User Permission",
            filters=filters or None,
            fields=["name", "user", "allow", "for_value", "applicable_for", "is_default", "hide_descendants", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "User Permission", "Listed user permission rows.")

    def _users_list_shared_documents(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user", "share_doctype", "share_name"))
        result = self.client.search_documents(
            "DocShare",
            filters=filters or None,
            fields=["name", "user", "share_doctype", "share_name", "read", "write", "share", "everyone", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "DocShare", "Listed shared document rows.")

    def _users_list_access_logs(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user",))
        result = self.client.search_documents(
            "Access Log",
            filters=filters or None,
            fields=["name", "user", "file_type", "method", "reference_document", "creation"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="creation desc",
        )
        return _users_read_result(result, "Access Log", "Listed access log rows.")

    def _users_list_activity_logs(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user", "subject"))
        result = self.client.search_documents(
            "Activity Log",
            filters=filters or None,
            fields=["name", "user", "subject", "operation", "reference_doctype", "reference_name", "creation"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="creation desc",
        )
        return _users_read_result(result, "Activity Log", "Listed activity log rows.")

    def _users_get_permission_metadata(self, args: dict[str, Any]) -> ToolResult:
        schema = self.client.get_doctype_schema(args["doctype"])
        if not schema.ok:
            return schema
        data = schema.data if isinstance(schema.data, dict) else {}
        permissions = data.get("permissions") or []
        docs = data.get("docs")
        if not permissions and isinstance(docs, list) and docs and isinstance(docs[0], dict):
            permissions = docs[0].get("permissions") or []
        return ToolResult(
            ok=True,
            status_code=schema.status_code,
            raw_status_code=schema.raw_status_code,
            data={
                "doctype": args["doctype"],
                "status": "Read Only",
                "summary": f"Permission metadata for {args['doctype']}.",
                "permissions": permissions or [],
                "next_actions": ["review_docperm_rows", "use_generic_schema_for_fields"],
                "risk": {"level": "L0", "changing_docperm_is_L5_ADMIN": True},
            },
            debug={"raw_schema": data},
        )

    def _users_build_metadata_permission_preview(self, user: str, doctype: str) -> ToolResult:
        user_doc = self.client.get_document("User", user)
        if not user_doc.ok:
            return user_doc
        schema = self.client.get_doctype_schema(doctype)
        if not schema.ok:
            return schema

        user_data = user_doc.data if isinstance(user_doc.data, dict) else {}
        schema_data = schema.data if isinstance(schema.data, dict) else {}
        role_names = {
            row.get("role")
            for row in user_data.get("roles", [])
            if isinstance(row, dict) and row.get("role")
        }
        role_names.discard(None)
        permission_rows = _extract_permission_rows(schema_data)
        effective, matched_rows = _metadata_effective_permissions(role_names, permission_rows)
        if not user_data.get("enabled", 1):
            effective = {key: False for key in effective}

        return ToolResult(
            ok=True,
            status_code=schema.status_code,
            raw_status_code=schema.raw_status_code,
            data={
                "doctype": doctype,
                "user": user,
                "roles": sorted(role_names),
                "enabled": user_data.get("enabled"),
                "permissions": effective,
                "matched_permission_rows": matched_rows,
            },
            debug={"raw_user": user_data, "raw_schema": schema_data},
        )

    def _users_preview_effective_permissions(self, args: dict[str, Any]) -> ToolResult:
        user = args["user"]
        doctype = args["doctype"]
        preview = self._users_build_metadata_permission_preview(user, doctype)
        if not preview.ok:
            return preview
        preview_data = preview.data
        user_permissions = None
        if args.get("include_user_permissions", True):
            permission_result = self.client.search_documents(
                "User Permission",
                filters={"user": user},
                fields=["name", "user", "allow", "for_value", "applicable_for", "is_default", "hide_descendants"],
                limit=100,
                order_by="modified desc",
            )
            if not permission_result.ok:
                return permission_result
            user_permissions = permission_result.data

        return ToolResult(
            ok=True,
            status_code=preview.status_code,
            raw_status_code=preview.raw_status_code,
            data={
                "doctype": doctype,
                "user": user,
                "status": "Preview",
                "summary": f"Previewed metadata-based effective permissions for {user} on {doctype}.",
                "roles": preview_data["roles"],
                "enabled": preview_data["enabled"],
                "permissions": preview_data["permissions"],
                "matched_permission_rows": preview_data["matched_permission_rows"],
                "user_permissions": user_permissions,
                "is_exact_runtime_evaluation": False,
                "next_actions": ["review_permissions", "use_agent_bridge_for_server_side_permission_check"],
                "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
            },
            debug=preview.debug,
        )

    def _users_check_server_permission(self, args: dict[str, Any]) -> ToolResult:
        user = args["user"]
        doctype = args["doctype"]
        action = (args["action"] or "read").strip().lower()
        if action not in USER_PERMISSION_ACTIONS:
            return ToolResult(
                ok=False,
                error=f"Unsupported permission action: {action}",
                error_type="validation_error",
                user_message="权限动作必须是 Frappe 支持的权限类型。",
                data={"supported_actions": list(USER_PERMISSION_ACTIONS)},
            )

        preview = self._users_build_metadata_permission_preview(user, doctype)
        if not preview.ok:
            return preview
        server = self.client.check_user_permission(
            user,
            doctype,
            action,
            docname=args.get("docname"),
            debug=args.get("debug", False),
        )
        if not server.ok:
            return server

        preview_data = preview.data if isinstance(preview.data, dict) else {}
        server_data = server.data if isinstance(server.data, dict) else {}
        metadata_allowed = bool((preview_data.get("permissions") or {}).get(action))
        server_allowed = bool(server_data.get("allowed"))
        difference = {
            "action": action,
            "metadata_preview_allowed": metadata_allowed,
            "server_runtime_allowed": server_allowed,
            "differs": metadata_allowed != server_allowed,
            "likely_reasons": _permission_difference_reasons(args.get("docname"), metadata_allowed, server_allowed),
        }

        return ToolResult(
            ok=True,
            status_code=server.status_code,
            raw_status_code=server.raw_status_code,
            data={
                "doctype": doctype,
                "docname": args.get("docname"),
                "user": user,
                "action": action,
                "status": "Checked",
                "summary": f"Checked server-side runtime permission for {user} to {action} {doctype}.",
                "allowed": server_allowed,
                "metadata_preview": {
                    "allowed": metadata_allowed,
                    "permissions": preview_data.get("permissions") or {},
                    "matched_permission_rows": preview_data.get("matched_permission_rows") or [],
                    "roles": preview_data.get("roles") or [],
                    "enabled": preview_data.get("enabled"),
                    "is_exact_runtime_evaluation": False,
                },
                "server_check": server_data,
                "differences": difference,
                "is_exact_runtime_evaluation": bool(server_data.get("is_exact_runtime_evaluation", True)),
                "next_actions": ["review_differences", "inspect_user_permissions_or_shares"],
                "risk": {"level": "L0", "requires_system_manager_in_agent_bridge": True},
            },
            debug={"metadata_preview": preview.debug, "raw_server_check": server_data},
        )

    def _users_preview_permission_policy_change(self, args: dict[str, Any]) -> ToolResult:
        changes = args.get("changes")
        if not isinstance(changes, list) or not changes:
            return ToolResult(
                ok=False,
                error="changes must be a non-empty list.",
                error_type="validation_error",
                user_message="权限策略预览需要至少一条 add、update 或 remove 变更。",
            )

        schema = self.client.get_doctype_schema(args["doctype"])
        if not schema.ok:
            return schema
        schema_data = schema.data if isinstance(schema.data, dict) else {}
        before_rows = [_permission_row_preview(row) for row in _extract_permission_rows(schema_data)]
        simulation = _simulate_permission_policy_changes(before_rows, changes)
        if isinstance(simulation, ToolResult):
            return simulation
        after_rows, diff, normalized_changes = simulation

        return ToolResult(
            ok=True,
            status_code=schema.status_code,
            raw_status_code=schema.raw_status_code,
            data={
                "doctype": args["doctype"],
                "status": "Permission Policy Preview",
                "summary": f"Previewed DocPerm-style policy changes for {args['doctype']} without writing ERPNext.",
                "before": before_rows,
                "after": after_rows,
                "diff": diff,
                "changes": normalized_changes,
                "requires_write_tool": "future_L5_ADMIN_docperm_change_tool",
                "next_actions": ["review_diff", "confirm_policy_owner_approval", "implement_dedicated_write_tool_if_needed"],
                "risk": {
                    "level": "L5_ADMIN",
                    "preview_only": True,
                    "writes_to_erpnext": False,
                    "changes_system_wide_permission_policy": True,
                },
            },
            debug={"raw_schema": schema_data},
        )

    def _users_create_user_draft(self, args: dict[str, Any]) -> ToolResult:
        data = {
            "email": args["email"],
            "first_name": args["first_name"],
            "last_name": args.get("last_name"),
            "enabled": 1 if args.get("enabled") is True else 0,
            "send_welcome_email": 1 if args.get("send_welcome_email") is True else 0,
            "user_type": args.get("user_type") or "System User",
            "role_profile_name": args.get("role_profile_name"),
        }
        roles = [{"role": role} for role in args.get("roles", [])]
        if roles:
            data["roles"] = roles
        data = _clean_mapping(data)
        guard = _require_admin_confirmation("create_user_draft", "User", args["email"], args.get("confirmation"), data)
        if guard:
            return guard
        result = self.client.create_document("User", data)
        return _users_write_result(result, "User", args["email"], "Created disabled user record for review.")

    def _users_set_user_enabled(self, args: dict[str, Any]) -> ToolResult:
        data = {"enabled": 1 if args["enabled"] else 0}
        action = "enable_user" if args["enabled"] else "disable_user"
        guard = _require_admin_confirmation(action, "User", args["user"], args.get("confirmation"), data)
        if guard:
            return guard
        result = self.client.update_document("User", args["user"], data)
        return _users_write_result(result, "User", args["user"], f"{'Enabled' if args['enabled'] else 'Disabled'} user.")

    def _users_assign_roles(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_admin_confirmation("assign_roles", "User", args["user"], args.get("confirmation"), {"mode": args["mode"], "roles": args["roles"]})
        if guard:
            return guard
        current = self.client.get_document("User", args["user"])
        if not current.ok:
            return current
        current_data = current.data if isinstance(current.data, dict) else {}
        existing = {
            row.get("role")
            for row in current_data.get("roles", [])
            if isinstance(row, dict) and row.get("role")
        }
        requested = set(args["roles"])
        if args["mode"] == "replace":
            next_roles = requested
        elif args["mode"] == "add":
            next_roles = existing | requested
        elif args["mode"] == "remove":
            next_roles = existing - requested
        else:
            return ToolResult(ok=False, error="Invalid role assignment mode.", error_type="validation_error", user_message="角色分配模式必须是 replace、add 或 remove。")
        result = self.client.update_document("User", args["user"], {"roles": [{"role": role} for role in sorted(next_roles)]})
        return _users_write_result(result, "User", args["user"], f"Updated roles for {args['user']}.")

    def _users_create_user_permission(self, args: dict[str, Any]) -> ToolResult:
        data = _clean_mapping(
            {
                "user": args["user"],
                "allow": args["allow"],
                "for_value": args["for_value"],
                "applicable_for": args.get("applicable_for"),
                "is_default": 1 if args.get("is_default") else 0,
                "hide_descendants": 1 if args.get("hide_descendants") else 0,
            }
        )
        guard = _require_admin_confirmation("create_user_permission", "User Permission", args["user"], args.get("confirmation"), data)
        if guard:
            return guard
        result = self.client.create_document("User Permission", data)
        return _users_write_result(result, "User Permission", data.get("for_value"), "Created user permission row.")

    def _users_delete_user_permission(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_admin_confirmation("delete_user_permission", "User Permission", args["name"], args.get("confirmation"), {"name": args["name"]})
        if guard:
            return guard
        result = self.client.delete_document("User Permission", args["name"])
        return _users_write_result(result, "User Permission", args["name"], "Deleted user permission row.")

    def _setup_item_master(self, args: dict[str, Any]) -> ToolResult:
        return self.client.setup_item_master()

    def _prepare_item_from_intent(self, args: dict[str, Any]) -> ToolResult:
        return self.client.prepare_item_from_intent(args["intent"])

    def _create_item_from_intent(self, args: dict[str, Any]) -> ToolResult:
        return self.client.create_item_from_intent(args["intent"])

    def _create_todo(self, args: dict[str, Any]) -> ToolResult:
        return self.client.create_todo(
            args["description"],
            allocated_to=args.get("allocated_to"),
            priority=args.get("priority", "Medium"),
            reference_type=args.get("reference_type"),
            reference_name=args.get("reference_name"),
            date=args.get("date"),
        )

    def _add_comment(self, args: dict[str, Any]) -> ToolResult:
        return self.client.add_comment(
            args["reference_doctype"],
            args["reference_name"],
            args["content"],
            comment_email=args.get("comment_email", "agent@example.com"),
            comment_by=args.get("comment_by", "Nexterp Agent"),
        )

    def _get_comments(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_comments(
            args["reference_doctype"],
            args["reference_name"],
            limit=args.get("limit", 20),
        )

    def _assign_to(self, args: dict[str, Any]) -> ToolResult:
        return self.client.assign_to(
            args["doctype"],
            args["name"],
            args["assign_to"],
            description=args.get("description"),
            priority=args.get("priority", "Medium"),
            date=args.get("date"),
        )

    def _clear_assignment(self, args: dict[str, Any]) -> ToolResult:
        return self.client.clear_assignment(args["doctype"], args["name"], args["assign_to"])

    def _attach_file(self, args: dict[str, Any]) -> ToolResult:
        return self.client.attach_file(
            args["doctype"],
            args["name"],
            args["file_path"],
            is_private=args.get("is_private", True),
            fieldname=args.get("fieldname"),
        )

    def _list_attachments(self, args: dict[str, Any]) -> ToolResult:
        return self.client.list_attachments(args["doctype"], args["name"])

    def _delete_attachment(self, args: dict[str, Any]) -> ToolResult:
        return self.client.delete_attachment(args["file_name"])

    def _assets_search_assets(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        for key in ("company", "asset_category", "location", "status", "item_code", "custodian"):
            if args.get(key) is not None:
                filters[key] = args[key]
        if args.get("query"):
            filters["asset_name"] = ["like", f"%{args['query']}%"]
        result = self.client.search_documents(
            "Asset",
            filters=filters or None,
            fields=args.get("fields")
            or [
                "name",
                "asset_name",
                "item_code",
                "asset_category",
                "company",
                "location",
                "custodian",
                "status",
                "docstatus",
                "gross_purchase_amount",
                "available_for_use_date",
            ],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )
        return _module_search_result(result, "Asset", filters, "L0")

    def _assets_search_asset_categories(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("query"):
            filters["asset_category_name"] = ["like", f"%{args['query']}%"]
        result = self.client.search_documents(
            "Asset Category",
            filters=filters or None,
            fields=args.get("fields") or ["name", "asset_category_name", "enable_cwip_accounting"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )
        return _module_search_result(result, "Asset Category", filters, "L0")

    def _assets_search_asset_locations(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("query"):
            filters["location_name"] = ["like", f"%{args['query']}%"]
        result = self.client.search_documents(
            "Asset Location",
            filters=filters or None,
            fields=args.get("fields") or ["name", "location_name", "parent_location", "is_group"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "lft asc"),
        )
        return _module_search_result(result, "Asset Location", filters, "L0")

    def _assets_get_financial_snapshot(self, args: dict[str, Any]) -> ToolResult:
        asset_result = self.client.get_document("Asset", args["asset"])
        if not asset_result.ok:
            return asset_result
        asset = asset_result.data if isinstance(asset_result.data, dict) else {}
        schedule_docs: list[dict[str, Any]] = []
        schedule_search_debug: Any = None

        if args.get("include_depreciation_schedules", True):
            filters: dict[str, Any] = {"asset": asset.get("name") or args["asset"]}
            if args.get("finance_book"):
                filters["finance_book"] = args["finance_book"]
            schedule_search = self.client.search_documents(
                "Asset Depreciation Schedule",
                filters=filters,
                fields=["name", "asset", "finance_book", "status", "docstatus", "value_after_depreciation"],
                limit=args.get("schedule_limit", 10),
                order_by="modified desc",
            )
            if not schedule_search.ok:
                return schedule_search
            schedule_search_debug = schedule_search.data
            for row in schedule_search.data if isinstance(schedule_search.data, list) else []:
                if not isinstance(row, dict) or not row.get("name"):
                    continue
                schedule_doc = self.client.get_document("Asset Depreciation Schedule", row["name"])
                if not schedule_doc.ok:
                    return schedule_doc
                if isinstance(schedule_doc.data, dict):
                    schedule_docs.append(schedule_doc.data)

        snapshot = _asset_financial_snapshot(
            asset,
            schedule_docs,
            finance_book=args.get("finance_book"),
            include_schedule_rows=args.get("include_schedule_rows", False),
        )
        return ToolResult(
            ok=True,
            status_code=asset_result.status_code,
            raw_status_code=asset_result.raw_status_code,
            data=snapshot,
            debug={"raw_asset": asset, "raw_depreciation_schedule_search": schedule_search_debug, "raw_depreciation_schedules": schedule_docs},
        )

    def _assets_get_depreciation_schedule(self, args: dict[str, Any]) -> ToolResult:
        filters: dict[str, Any] = {"asset": args["asset"]}
        if args.get("finance_book"):
            filters["finance_book"] = args["finance_book"]
        if args.get("status"):
            filters["status"] = args["status"]
        search = self.client.search_documents(
            "Asset Depreciation Schedule",
            filters=filters,
            fields=args.get("fields") or ["name", "asset", "finance_book", "status", "docstatus", "value_after_depreciation"],
            limit=args.get("limit", 20),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )
        if not search.ok:
            return search

        schedules: list[dict[str, Any]] = []
        raw_rows = search.data if isinstance(search.data, list) else []
        if args.get("include_rows", False):
            for row in raw_rows:
                if not isinstance(row, dict) or not row.get("name"):
                    continue
                doc = self.client.get_document("Asset Depreciation Schedule", row["name"])
                if not doc.ok:
                    return doc
                if isinstance(doc.data, dict):
                    schedules.append(_asset_depreciation_schedule_preview(doc.data, args.get("only_due_before")))
        else:
            schedules = [dict(row) for row in raw_rows if isinstance(row, dict)]

        return ToolResult(
            ok=True,
            status_code=search.status_code,
            raw_status_code=search.raw_status_code,
            data={
                "doctype": "Asset Depreciation Schedule",
                "asset": args["asset"],
                "status": "Read Only",
                "summary": f"Fetched {len(schedules)} depreciation schedule record(s) for Asset {args['asset']}.",
                "filters": filters,
                "records": schedules,
                "count": len(schedules),
                "next_actions": ["review_due_rows", "use_confirmed_financial_tool_for_depreciation_posting"],
                "risk": {"level": "L0", "creates_financial_posting": False},
            },
            debug={"raw_search": search.data},
        )

    def _assets_create_asset_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Asset", args["data"])
        return _module_doc_result(
            self.client.create_document("Asset", data),
            "Asset",
            "L3",
            "Created Asset draft.",
            ["review_asset_master", "confirm_capitalization"],
            requires_confirmation_for_submit=True,
        )

    def _assets_create_movement_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Asset Movement", args["data"])
        return _module_doc_result(
            self.client.create_document("Asset Movement", data),
            "Asset Movement",
            "L3",
            "Created Asset Movement draft.",
            ["review_asset_rows", "review_locations", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _assets_create_maintenance_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Asset Maintenance", args["data"])
        return _module_doc_result(
            self.client.create_document("Asset Maintenance", data),
            "Asset Maintenance",
            "L3",
            "Created Asset Maintenance draft.",
            ["review_maintenance_tasks", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _assets_create_maintenance_log_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Asset Maintenance Log", args["data"])
        return _module_doc_result(
            self.client.create_document("Asset Maintenance Log", data),
            "Asset Maintenance Log",
            "L3",
            "Created Asset Maintenance Log draft.",
            ["review_work_done", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _assets_create_repair_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Asset Repair", args["data"])
        return _module_doc_result(
            self.client.create_document("Asset Repair", data),
            "Asset Repair",
            "L3",
            "Created Asset Repair draft.",
            ["review_repair_costs", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _assets_create_value_adjustment_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _draft_doc("Asset Value Adjustment", args["data"])
        return _module_doc_result(
            self.client.create_document("Asset Value Adjustment", data),
            "Asset Value Adjustment",
            "L3",
            "Created Asset Value Adjustment draft.",
            ["review_financial_impact", "confirm_submit"],
            requires_confirmation_for_submit=True,
        )

    def _assets_prepare_disposal_or_sale(self, args: dict[str, Any]) -> ToolResult:
        asset = self.client.get_document("Asset", args["asset"])
        if not asset.ok:
            return asset
        action = args.get("action", "dispose")
        data = asset.data if isinstance(asset.data, dict) else {}
        return ToolResult(
            ok=True,
            status_code=asset.status_code,
            raw_status_code=asset.raw_status_code,
            data={
                "doctype": "Asset",
                "name": data.get("name") or args["asset"],
                "action": action,
                "status": "Prepared",
                "summary": f"Prepared {action} review for Asset {data.get('name') or args['asset']}.",
                "next_actions": [
                    "review_asset_status",
                    "create_accounting_or_sales_draft_with_accounting_owned_tools",
                    "confirm_submit_or_posting",
                ],
                "risk": {
                    "level": "L5_FINANCIAL",
                    "requires_confirmation_for_submit": True,
                    "reason": "Asset disposal or sale can create GL, gain/loss, or invoice impact.",
                },
            },
            debug={"raw_document": data},
        )

    def _assets_submit_document(self, args: dict[str, Any]) -> ToolResult:
        doctype = args["doctype"]
        if doctype not in ASSET_SUBMITTABLE_DOCTYPES:
            return ToolResult(
                ok=False,
                error=f"Unsupported asset submit DocType: {doctype}",
                error_type="validation_error",
                user_message="此资产提交工具只支持 Asset、Asset Movement、Asset Maintenance、Asset Maintenance Log、Asset Repair、Asset Value Adjustment。",
            )
        guard = _require_asset_confirmation(doctype, args["name"], args.get("confirmation"))
        if guard:
            return guard
        risk_level = "L5_FINANCIAL" if doctype in ASSET_FINANCIAL_DOCTYPES else "L4"
        return _module_doc_result(
            self.client.submit_document(doctype, args["name"]),
            doctype,
            risk_level,
            f"Submitted {doctype}.",
            ["review_post_submit_status", "audit_asset_lifecycle"],
            requires_confirmation_for_submit=True,
        )

    def _buying_search_suppliers(self, args: dict[str, Any]) -> ToolResult:
        filters: dict[str, Any] = {}
        if args.get("supplier_group"):
            filters["supplier_group"] = args["supplier_group"]
        if args.get("supplier_type"):
            filters["supplier_type"] = args["supplier_type"]
        if args.get("query"):
            filters["supplier_name"] = ["like", f"%{args['query']}%"]
        for key in ("disabled", "is_frozen", "on_hold"):
            if args.get(key) is not None:
                filters[key] = 1 if args[key] is True else 0 if args[key] is False else args[key]
        return self.client.search_documents(
            "Supplier",
            filters=filters or None,
            fields=args.get("fields")
            or [
                "name",
                "supplier_name",
                "supplier_group",
                "supplier_type",
                "disabled",
                "is_frozen",
                "on_hold",
                "warn_rfqs",
                "prevent_rfqs",
                "warn_pos",
                "prevent_pos",
            ],
            limit=args.get("limit", 50),
            order_by="modified desc",
        )

    def _buying_search_supplier_scorecards(self, args: dict[str, Any]) -> ToolResult:
        filters: dict[str, Any] = {}
        for key in ("supplier", "status"):
            if args.get(key):
                filters[key] = args[key]
        result = self.client.search_documents(
            "Supplier Scorecard",
            filters=filters or None,
            fields=args.get("fields")
            or [
                "name",
                "supplier",
                "status",
                "supplier_score",
                "warn_rfqs",
                "prevent_rfqs",
                "warn_pos",
                "prevent_pos",
                "modified",
            ],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )
        return _module_search_result(result, "Supplier Scorecard", filters, "L0")

    def _buying_get_supplier_procurement_profile(self, args: dict[str, Any]) -> ToolResult:
        supplier_result = self.client.get_document("Supplier", args["supplier"])
        if not supplier_result.ok:
            return supplier_result
        supplier = supplier_result.data if isinstance(supplier_result.data, dict) else {}

        scorecards_result = self.client.search_documents(
            "Supplier Scorecard",
            filters={"supplier": args["supplier"]},
            fields=[
                "name",
                "supplier",
                "status",
                "supplier_score",
                "warn_rfqs",
                "prevent_rfqs",
                "warn_pos",
                "prevent_pos",
                "modified",
            ],
            limit=args.get("scorecard_limit", 5),
            order_by="modified desc",
        )
        if not scorecards_result.ok:
            return scorecards_result
        scorecards = scorecards_result.data if isinstance(scorecards_result.data, list) else []

        item_suppliers: list[dict[str, Any]] = []
        item_prices: list[dict[str, Any]] = []
        item_code = args.get("item_code")
        if item_code:
            item_supplier_result = self.client.search_documents(
                "Item Supplier",
                filters={"parent": item_code, "supplier": args["supplier"]},
                fields=["name", "parent", "supplier", "supplier_part_no"],
                limit=20,
                order_by="modified desc",
            )
            if not item_supplier_result.ok:
                return item_supplier_result
            item_suppliers = item_supplier_result.data if isinstance(item_supplier_result.data, list) else []

            price_filters: dict[str, Any] = {"item_code": item_code, "buying": 1}
            if args.get("currency"):
                price_filters["currency"] = args["currency"]
            if args.get("price_list"):
                price_filters["price_list"] = args["price_list"]
            if args.get("supplier"):
                price_filters["supplier"] = args["supplier"]
            item_price_result = self.client.search_documents(
                "Item Price",
                filters=price_filters,
                fields=["name", "item_code", "price_list", "price_list_rate", "currency", "supplier", "valid_from", "valid_upto"],
                limit=20,
                order_by="valid_from desc",
            )
            if not item_price_result.ok:
                return item_price_result
            item_prices = item_price_result.data if isinstance(item_price_result.data, list) else []

        eligibility = _supplier_procurement_eligibility(supplier, scorecards)
        return ToolResult(
            ok=True,
            status_code=supplier_result.status_code,
            raw_status_code=supplier_result.raw_status_code,
            data={
                "doctype": "Supplier",
                "supplier": args["supplier"],
                "status": "Profile Ready",
                "summary": f"Prepared procurement profile for Supplier {args['supplier']}.",
                "supplier_profile": {
                    "name": supplier.get("name") or args["supplier"],
                    "supplier_name": supplier.get("supplier_name"),
                    "supplier_group": supplier.get("supplier_group"),
                    "supplier_type": supplier.get("supplier_type"),
                    "disabled": _truthy(supplier.get("disabled")),
                    "is_frozen": _truthy(supplier.get("is_frozen")),
                    "on_hold": _truthy(supplier.get("on_hold")),
                    "warn_rfqs": _truthy(supplier.get("warn_rfqs")),
                    "prevent_rfqs": _truthy(supplier.get("prevent_rfqs")),
                    "warn_pos": _truthy(supplier.get("warn_pos")),
                    "prevent_pos": _truthy(supplier.get("prevent_pos")),
                },
                "scorecards": scorecards,
                "item_suppliers": item_suppliers,
                "item_prices": item_prices,
                "eligibility": eligibility,
                "next_actions": ["review_supplier_warnings", "preview_rfq_or_po_flow"],
                "risk": {"level": "L1", "creates_procurement_document": False},
            },
            debug={"raw_supplier": supplier},
        )

    def _buying_create_supplier_group_draft(self, args: dict[str, Any]) -> ToolResult:
        data = {
            "doctype": "Supplier Group",
            "supplier_group_name": args["supplier_group_name"],
            "parent_supplier_group": args.get("parent_supplier_group"),
            "is_group": 1 if args.get("is_group", True) else 0,
        }
        return _module_draft_result(
            self.client.create_document("Supplier Group", _without_empty(data)),
            doctype="Supplier Group",
            summary=f"Created Supplier Group draft/master for {args['supplier_group_name']}.",
            risk_level="L3",
        )

    def _buying_create_supplier_draft(self, args: dict[str, Any]) -> ToolResult:
        data = _without_empty(
            {
                "doctype": "Supplier",
                "supplier_name": args["supplier_name"],
                "supplier_group": args.get("supplier_group"),
                "supplier_type": args.get("supplier_type", "Company"),
                "country": args.get("country"),
                "tax_id": args.get("tax_id"),
                "default_currency": args.get("default_currency"),
                "disabled": 0,
            }
        )
        return _module_draft_result(
            self.client.create_document("Supplier", data),
            doctype="Supplier",
            summary=f"Created Supplier draft for {args['supplier_name']}.",
            risk_level="L3",
        )

    def _buying_create_material_request_draft(self, args: dict[str, Any]) -> ToolResult:
        items = [self._normalize_buying_item_row(item) for item in args["items"]]
        if any(not item.get("item_code") for item in items):
            return _item_resolution_error("采购申请草稿中存在无法解析 item_code 的行。")
        data = _without_empty(
            {
                "doctype": "Material Request",
                "material_request_type": args.get("material_request_type", "Purchase"),
                "schedule_date": args.get("schedule_date"),
                "company": args.get("company"),
                "items": items,
                "docstatus": 0,
            }
        )
        return _module_draft_result(
            self.client.create_document("Material Request", data),
            doctype="Material Request",
            summary=f"Created Material Request draft with {len(items)} item rows.",
            risk_level="L3",
            submit_tool="erpnext.buying.submit_document",
        )

    def _buying_create_request_for_quotation_draft(self, args: dict[str, Any]) -> ToolResult:
        items = [self._normalize_buying_item_row(item) for item in args["items"]]
        if any(not item.get("item_code") for item in items):
            return _item_resolution_error("询价单草稿中存在无法解析 item_code 的行。")
        data = _without_empty(
            {
                "doctype": "Request for Quotation",
                "transaction_date": args.get("transaction_date"),
                "schedule_date": args.get("schedule_date"),
                "suppliers": [{"supplier": supplier} if isinstance(supplier, str) else supplier for supplier in args["suppliers"]],
                "items": items,
                "docstatus": 0,
            }
        )
        return _module_draft_result(
            self.client.create_document("Request for Quotation", data),
            doctype="Request for Quotation",
            summary=f"Created Request for Quotation draft for {len(data['suppliers'])} suppliers.",
            risk_level="L3",
            submit_tool="erpnext.buying.submit_document",
        )

    def _buying_create_supplier_quotation_draft(self, args: dict[str, Any]) -> ToolResult:
        items = [self._normalize_buying_item_row(item) for item in args["items"]]
        if any(not item.get("item_code") for item in items):
            return _item_resolution_error("供应商报价草稿中存在无法解析 item_code 的行。")
        data = _without_empty(
            {
                "doctype": "Supplier Quotation",
                "supplier": args["supplier"],
                "transaction_date": args.get("transaction_date"),
                "valid_till": args.get("valid_till"),
                "currency": args.get("currency"),
                "items": items,
                "docstatus": 0,
            }
        )
        return _module_draft_result(
            self.client.create_document("Supplier Quotation", data),
            doctype="Supplier Quotation",
            summary=f"Created Supplier Quotation draft for {args['supplier']} with {len(items)} item rows.",
            risk_level="L3",
            submit_tool="erpnext.buying.submit_document",
        )

    def _buying_create_purchase_order_draft(self, args: dict[str, Any]) -> ToolResult:
        items = [self._normalize_buying_item_row(item) for item in args["items"]]
        if any(not item.get("item_code") for item in items):
            return _item_resolution_error("采购订单草稿中存在无法解析 item_code 的行。")
        data = _without_empty(
            {
                "doctype": "Purchase Order",
                "supplier": args["supplier"],
                "transaction_date": args.get("transaction_date"),
                "schedule_date": args.get("schedule_date"),
                "company": args.get("company"),
                "currency": args.get("currency"),
                "items": items,
                "docstatus": 0,
            }
        )
        return _module_draft_result(
            self.client.create_document("Purchase Order", data),
            doctype="Purchase Order",
            summary=f"Created Purchase Order draft for {args['supplier']} with {len(items)} item rows.",
            risk_level="L3",
            submit_tool="erpnext.buying.submit_document",
        )

    def _buying_create_purchase_receipt_draft(self, args: dict[str, Any]) -> ToolResult:
        items = [self._normalize_buying_item_row(item) for item in args["items"]]
        if any(not item.get("item_code") for item in items):
            return _item_resolution_error("采购收货草稿中存在无法解析 item_code 的行。")
        data = _without_empty(
            {
                "doctype": "Purchase Receipt",
                "supplier": args["supplier"],
                "posting_date": args.get("posting_date"),
                "company": args.get("company"),
                "items": items,
                "docstatus": 0,
            }
        )
        return _module_draft_result(
            self.client.create_document("Purchase Receipt", data),
            doctype="Purchase Receipt",
            summary=f"Created Purchase Receipt draft for {args['supplier']} with {len(items)} item rows.",
            risk_level="L3",
            submit_tool="erpnext.buying.submit_document",
        )

    def _buying_generate_purchase_suggestions(self, args: dict[str, Any]) -> ToolResult:
        result = self.client.call_method(
            "agent_bridge.api.generate_purchase_suggestions",
            args,
            http_method="POST",
        )
        if not result.ok:
            return result
        count = result.data.get("count", 0) if isinstance(result.data, dict) else 0
        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data={
                "doctype": None,
                "name": None,
                "docstatus": None,
                "status": "Suggestions Generated",
                "summary": f"Generated {count} purchase suggestion rows.",
                "next_actions": ["review_suggestions", "create_material_request_draft"],
                "risk": {"level": "L0", "requires_confirmation_for_submit": False},
                "suggestions": result.data,
            },
            debug={"raw_result": result.data},
        )

    def _buying_search_item_suppliers(self, args: dict[str, Any]) -> ToolResult:
        filters: dict[str, Any] = {}
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        if item_code:
            filters["parent"] = item_code
        if args.get("supplier"):
            filters["supplier"] = args["supplier"]
        return self.client.search_documents(
            "Item Supplier",
            filters=filters or None,
            fields=args.get("fields") or ["name", "parent", "supplier", "supplier_part_no"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "modified desc"),
        )

    def _buying_search_item_prices(self, args: dict[str, Any]) -> ToolResult:
        filters: dict[str, Any] = {}
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        if item_code:
            filters["item_code"] = item_code
        if args.get("price_list"):
            filters["price_list"] = args["price_list"]
        filters["buying"] = 1 if args.get("buying", True) else 0
        return self.client.search_documents(
            "Item Price",
            filters=filters or None,
            fields=args.get("fields") or ["name", "item_code", "price_list", "price_list_rate", "currency", "buying", "valid_from", "valid_upto"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "valid_from desc"),
        )

    def _buying_get_buying_settings(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_document("Buying Settings", "Buying Settings")

    def _buying_run_purchase_analysis(self, args: dict[str, Any]) -> ToolResult:
        report_name = args.get("report_name", "Purchase Analytics")
        filters = _report_filters(args)
        return _module_report_result(self.client.run_report(report_name, filters=filters), report_name, filters)

    def _buying_compare_supplier_quotations(self, args: dict[str, Any]) -> ToolResult:
        names = args["supplier_quotations"]
        if not isinstance(names, list) or len(names) < 2:
            return ToolResult(
                ok=False,
                error="At least two Supplier Quotation names are required for comparison.",
                error_type="validation_error",
                user_message="供应商报价比较至少需要两张 Supplier Quotation。",
                data={
                    "status": "invalid_input",
                    "summary": "Provide at least two Supplier Quotation document names.",
                    "next_actions": ["provide_supplier_quotation_names", "retry_comparison"],
                    "risk": {"level": "L1", "requires_confirmation_for_submit": False},
                },
            )
        include_drafts = args.get("include_drafts", False)
        quotations: list[dict[str, Any]] = []
        fetch_errors: list[dict[str, Any]] = []
        for name in names:
            result = self.client.get_document("Supplier Quotation", name)
            if not result.ok or not isinstance(result.data, dict):
                fetch_errors.append({"name": name, "error": result.error, "error_type": result.error_type})
                continue
            quotations.append(result.data)
        if fetch_errors:
            return ToolResult(
                ok=False,
                error="Unable to read all Supplier Quotation documents for comparison.",
                error_type="quotation_read_failed",
                user_message="部分供应商报价单无法读取，无法生成可靠比较。",
                data={
                    "status": "read_failed",
                    "summary": f"Failed to read {len(fetch_errors)} Supplier Quotation documents.",
                    "fetch_errors": fetch_errors,
                    "next_actions": ["check_supplier_quotation_names", "retry_comparison"],
                    "risk": {"level": "L1", "requires_confirmation_for_submit": False},
                },
            )
        return _supplier_quotation_comparison_result(quotations, names, include_drafts=include_drafts)

    def _buying_submit_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_buying_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if guard:
            return guard
        return _module_doc_result(
            self.client.submit_document(args["doctype"], args["name"]),
            args["doctype"],
            "L4",
            f"Submitted {args['doctype']} {args['name']}.",
            ["monitor_status", "review_downstream_impacts"],
            requires_confirmation_for_submit=True,
        )

    def _normalize_buying_item_row(self, item: dict[str, Any]) -> dict[str, Any]:
        row = dict(item)
        if row.get("selected_item_code") and not row.get("selection_confirmed"):
            row.pop("item_code", None)
            return row
        if not row.get("item_code"):
            row["item_code"] = self._stock_item_code_from_args(row)
        if row.get("item_code"):
            item_doc = self.client.get_document("Item", str(row["item_code"]))
            if not item_doc.ok or not isinstance(item_doc.data, dict) or item_doc.data.get("disabled"):
                row.pop("item_code", None)
                return row
            row["uom"] = row.get("uom") or item_doc.data.get("stock_uom")
            row["item_name"] = item_doc.data.get("item_name")
        allowed_fields = {
            "item_code",
            "item_name",
            "qty",
            "uom",
            "schedule_date",
            "warehouse",
            "rate",
            "price_list_rate",
            "conversion_factor",
            "description",
            "material_request",
            "material_request_item",
            "request_for_quotation",
            "supplier_quotation",
            "purchase_order",
            "purchase_order_item",
        }
        return _without_empty({field: row.get(field) for field in allowed_fields})

    def _stock_get_balance(self, args: dict[str, Any]) -> ToolResult:
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        return self.client.get_stock_balance(
            item_code,
            warehouse=args.get("warehouse"),
            limit=args.get("limit", 100),
        )

    def _stock_get_item_locations(self, args: dict[str, Any]) -> ToolResult:
        item_code = self._stock_item_code_from_args(args)
        if not item_code:
            return _item_resolution_error()
        return self.client.get_item_stock_locations(
            item_code,
            include_zero=args.get("include_zero", False),
            limit=args.get("limit", 100),
        )

    def _stock_get_ledger_entries(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_stock_ledger_entries(
            item_code=args.get("item_code"),
            warehouse=args.get("warehouse"),
            voucher_type=args.get("voucher_type"),
            voucher_no=args.get("voucher_no"),
            limit=args.get("limit", 50),
        )

    def _stock_get_stock_settings(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_stock_settings()

    def _stock_resolve_item(self, args: dict[str, Any]) -> ToolResult:
        query = args["query"]
        specs = args.get("specs")
        item_group = args.get("item_group")
        limit = args.get("limit", 10)
        enabled_only = args.get("enabled_only", True)

        erpnext_result = MaterialSearch(self.client).search_items(
            query,
            specs=specs,
            item_group=item_group,
            enabled_only=enabled_only,
            limit=limit,
        )

        catalog_result: dict[str, Any] | None = None
        dsn = args.get("catalog_database_url") or os.getenv("MATERIAL_CATALOG_DATABASE_URL")
        if dsn:
            try:
                catalog_result = MaterialSearch(PostgresCatalogSearchClient(dsn)).search_items(
                    query,
                    specs=specs,
                    item_group=item_group,
                    enabled_only=enabled_only,
                    limit=limit,
                )
            except RuntimeError as exc:
                catalog_result = {
                    "status": "unavailable",
                    "error": str(exc),
                    "candidates": [],
                    "questions": ["PostgreSQL 物料 catalog 不可用，请先用 ERPNext Item 候选或补充物料编码。"],
                }

        selected_item_code = _select_ready_item(erpnext_result)
        return ToolResult(
            ok=True,
            data={
                "query": query,
                "selected_item_code": selected_item_code,
                "status": "ready" if selected_item_code else "needs_confirmation",
                "erpnext": erpnext_result,
                "catalog": catalog_result,
                "workflow": [
                    "PostgreSQL catalog 用于召回采购原始名称、别名和 reviewed candidate。",
                    "ERPNext Item 是最终库存动作使用的物料主数据。",
                    "只有 ERPNext 搜索结果 ready 且未禁用时，库存工具才自动带入 item_code。",
                ],
            },
        )

    def _stock_create_entry_draft(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args)
        data["items"] = [self._normalize_stock_item_row(item) for item in args["items"]]
        if any(not item.get("item_code") for item in data["items"]):
            return _item_resolution_error("库存移动草稿中存在无法解析 item_code 的行。")
        result = self.client.create_stock_entry_draft(data)
        return _stock_draft_result(
            result,
            doctype="Stock Entry",
            summary=f"Created Stock Entry draft with {len(data['items'])} item rows.",
        )

    def _stock_create_reconciliation_draft(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args)
        data["items"] = [self._normalize_stock_item_row(item) for item in args["items"]]
        if any(not item.get("item_code") for item in data["items"]):
            return _item_resolution_error("库存盘点/调整草稿中存在无法解析 item_code 的行。")
        result = self.client.create_stock_reconciliation_draft(data)
        return _stock_draft_result(
            result,
            doctype="Stock Reconciliation",
            summary=f"Created Stock Reconciliation draft with {len(data['items'])} counted item rows.",
        )

    def _stock_search_batches(self, args: dict[str, Any]) -> ToolResult:
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        return self.client.search_batches(
            item_code=item_code,
            query=args.get("query"),
            limit=args.get("limit", 50),
        )

    def _stock_list_batch_balances(self, args: dict[str, Any]) -> ToolResult:
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        if not item_code:
            return _item_resolution_error("批次余额查询中无法解析 item_code。")

        batch_query = args.get("batch_no") or args.get("query")
        batches_result = self.client.search_batches(
            item_code=item_code,
            query=batch_query,
            limit=args.get("batch_limit", args.get("limit", 50)),
        )
        if not batches_result.ok:
            return batches_result
        raw_batches = [row for row in batches_result.data if isinstance(row, dict)] if isinstance(batches_result.data, list) else []
        batch_names = {
            str(row.get("name") or row.get("batch_id"))
            for row in raw_batches
            if row.get("name") or row.get("batch_id")
        }

        filters: dict[str, Any] = {"item_code": item_code, "is_cancelled": 0}
        if args.get("warehouse"):
            filters["warehouse"] = args["warehouse"]
        if args.get("batch_no"):
            filters["batch_no"] = args["batch_no"]
        elif batch_names:
            filters["batch_no"] = ["in", sorted(batch_names)]
        if args.get("as_of_date"):
            filters["posting_date"] = ["<=", args["as_of_date"]]
        ledger_result = self.client.search_documents(
            "Stock Ledger Entry",
            filters=filters,
            fields=[
                "name",
                "item_code",
                "warehouse",
                "posting_date",
                "posting_time",
                "actual_qty",
                "qty_after_transaction",
                "valuation_rate",
                "stock_value",
                "batch_no",
                "is_cancelled",
            ],
            limit=args.get("ledger_limit", 500),
            order_by="posting_date desc, posting_time desc, creation desc",
        )
        if not ledger_result.ok:
            return ledger_result

        batch_meta = {str(row.get("name") or row.get("batch_id")): row for row in raw_batches if row.get("name") or row.get("batch_id")}
        ledger_rows = ledger_result.data if isinstance(ledger_result.data, list) else []
        balances = _stock_batch_balance_rows(
            item_code,
            batch_meta,
            ledger_rows,
            include_expired=args.get("include_expired", False),
            include_zero=args.get("include_zero", False),
            as_of_date=args.get("as_of_date"),
        )
        return ToolResult(
            ok=True,
            status_code=ledger_result.status_code,
            raw_status_code=ledger_result.raw_status_code,
            data={
                "doctype": "Batch",
                "item_code": item_code,
                "status": "Read Only",
                "summary": f"Fetched {len(balances)} batch balance row(s) for Item {item_code}.",
                "filters": filters,
                "records": balances,
                "count": len(balances),
                "next_actions": ["review_batch_availability", "select_batch_for_stock_entry_or_pick_list"],
                "risk": {"level": "L0", "moves_stock": False},
            },
            debug={"raw_batches": raw_batches, "raw_ledger_entries": ledger_rows},
        )

    def _stock_search_serial_numbers(self, args: dict[str, Any]) -> ToolResult:
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        return self.client.search_serial_numbers(
            item_code=item_code,
            warehouse=args.get("warehouse"),
            status=args.get("status"),
            query=args.get("query"),
            limit=args.get("limit", 50),
        )

    def _stock_create_batch(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args["data"])
        if not data.get("item") and not data.get("item_code"):
            item_code = self._stock_item_code_from_args(data)
            if item_code:
                data["item"] = item_code
        if data.get("item_code") and not data.get("item"):
            data["item"] = data.pop("item_code")
        if not data.get("item"):
            return _item_resolution_error("批次创建中存在无法解析 item_code/item 的行。")
        result = self.client.create_batch(data)
        return _stock_master_result(result, doctype="Batch", action="Created Batch traceability record.")

    def _stock_update_batch(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_traceability_confirmation("Batch", args["name"], args.get("confirmation"))
        if guard:
            return guard
        result = self.client.update_batch(args["name"], args["data"])
        return _stock_traceability_result(result, doctype="Batch", action="Updated Batch traceability record.")

    def _stock_create_serial_no(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args["data"])
        if not data.get("item_code"):
            item_code = self._stock_item_code_from_args(data)
            if item_code:
                data["item_code"] = item_code
        if not data.get("item_code"):
            return _item_resolution_error("序列号创建中存在无法解析 item_code 的行。")
        result = self.client.create_serial_no(data)
        return _stock_master_result(result, doctype="Serial No", action="Created Serial No traceability record.")

    def _stock_update_serial_no(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_traceability_confirmation("Serial No", args["name"], args.get("confirmation"))
        if guard:
            return guard
        result = self.client.update_serial_no(args["name"], args["data"])
        return _stock_traceability_result(result, doctype="Serial No", action="Updated Serial No traceability record.")

    def _stock_list_pick_lists(self, args: dict[str, Any]) -> ToolResult:
        return self.client.list_pick_lists(
            purpose=args.get("purpose"),
            status=args.get("status"),
            customer=args.get("customer"),
            limit=args.get("limit", 50),
        )

    def _stock_create_pick_list_draft(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args)
        data["locations"] = [self._normalize_pick_list_location(row) for row in args.get("locations", [])]
        if any(not row.get("item_code") for row in data["locations"]):
            return _item_resolution_error("拣货单草稿中存在无法解析 item_code 的行。")
        result = self.client.create_pick_list_draft(data)
        return _stock_draft_result(
            result,
            doctype="Pick List",
            summary=f"Created Pick List draft with {len(data['locations'])} location rows.",
        )

    def _stock_list_reservations(self, args: dict[str, Any]) -> ToolResult:
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        return self.client.list_stock_reservations(
            item_code=item_code,
            warehouse=args.get("warehouse"),
            voucher_type=args.get("voucher_type"),
            voucher_no=args.get("voucher_no"),
            status=args.get("status"),
            limit=args.get("limit", 50),
        )

    def _stock_create_reservation_draft(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args)
        if not data.get("item_code"):
            data["item_code"] = self._stock_item_code_from_args(data)
        if not data.get("item_code"):
            return _item_resolution_error("库存预留草稿中存在无法解析 item_code 的行。")
        result = self.client.create_stock_reservation_draft(data)
        return _stock_draft_result(
            result,
            doctype="Stock Reservation Entry",
            summary=f"Created Stock Reservation Entry draft for {data['item_code']}.",
        )

    def _stock_preview_valuation(self, args: dict[str, Any]) -> ToolResult:
        items = [self._normalize_stock_preview_row(row) for row in args["items"]]
        if any(not row.get("item_code") for row in items):
            return _item_resolution_error("库存估值预览中存在无法解析 item_code 的行。")
        result = self.client.preview_stock_valuation(items)
        return _stock_preview_result(
            result,
            summary=f"Previewed stock valuation impact for {len(items)} item rows.",
            next_actions=["review_valuation_preview", "create_stock_entry_draft", "create_reconciliation_draft"],
        )

    def _stock_allocate_shortages(self, args: dict[str, Any]) -> ToolResult:
        items = [self._normalize_stock_preview_row(row) for row in args["items"]]
        if any(not row.get("item_code") for row in items):
            return _item_resolution_error("缺料分配预览中存在无法解析 item_code 的行。")
        result = self.client.allocate_stock_shortages(items)
        return _stock_preview_result(
            result,
            summary=f"Previewed stock allocation and shortages for {len(items)} demand rows.",
            next_actions=["review_shortages", "create_pick_list_draft", "create_reservation_draft", "request_purchase_or_transfer"],
        )

    def _stock_list_delivery_notes(self, args: dict[str, Any]) -> ToolResult:
        return self.client.list_delivery_notes(
            customer=args.get("customer"),
            status=args.get("status"),
            docstatus=args.get("docstatus"),
            limit=args.get("limit", 50),
        )

    def _stock_list_purchase_receipts(self, args: dict[str, Any]) -> ToolResult:
        return self.client.list_purchase_receipts(
            supplier=args.get("supplier"),
            status=args.get("status"),
            docstatus=args.get("docstatus"),
            limit=args.get("limit", 50),
        )

    def _stock_get_document_impact(self, args: dict[str, Any]) -> ToolResult:
        doctype = args["doctype"]
        if doctype not in {"Delivery Note", "Purchase Receipt"}:
            return ToolResult(
                ok=False,
                error=f"Unsupported stock boundary DocType: {doctype}",
                error_type="validation_error",
                user_message="库存边界影响查看只支持 Delivery Note 和 Purchase Receipt。",
            )
        document = self.client.get_document(doctype, args["name"])
        if not document.ok:
            return document
        ledger = self.client.get_stock_ledger_entries(
            voucher_type=doctype,
            voucher_no=args["name"],
            limit=args.get("limit", 100),
        )
        if not ledger.ok:
            return ledger
        return _stock_document_impact_result(doctype, args["name"], document.data, ledger.data)

    def _stock_list_item_reorders(self, args: dict[str, Any]) -> ToolResult:
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        return self.client.list_item_reorders(
            item_code=item_code,
            warehouse=args.get("warehouse"),
            material_request_type=args.get("material_request_type"),
            limit=args.get("limit", 100),
        )

    def _stock_list_quality_inspections(self, args: dict[str, Any]) -> ToolResult:
        item_code = args.get("item_code")
        if not item_code and args.get("item_query"):
            item_code = self._stock_item_code_from_args(args)
        return self.client.list_quality_inspections(
            item_code=item_code,
            reference_type=args.get("reference_type"),
            reference_name=args.get("reference_name"),
            inspection_type=args.get("inspection_type"),
            status=args.get("status"),
            docstatus=args.get("docstatus"),
            limit=args.get("limit", 50),
        )

    def _stock_list_warehouses(self, args: dict[str, Any]) -> ToolResult:
        return self.client.list_warehouses(
            company=args.get("company"),
            query=args.get("query"),
            limit=args.get("limit", 100),
        )

    def _stock_create_warehouse(self, args: dict[str, Any]) -> ToolResult:
        result = self.client.create_warehouse(args["data"])
        return _stock_master_result(result, doctype="Warehouse", action="Created Warehouse master record.")

    def _stock_update_warehouse(self, args: dict[str, Any]) -> ToolResult:
        result = self.client.update_warehouse(args["name"], args["data"])
        return _stock_master_result(result, doctype="Warehouse", action="Updated Warehouse master record.")

    def _stock_list_item_groups(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("parent_item_group"):
            filters["parent_item_group"] = args["parent_item_group"]
        if args.get("is_group") is not None:
            filters["is_group"] = args["is_group"]
        if args.get("query"):
            filters["item_group_name"] = ["like", f"%{args['query']}%"]
        result = self.client.search_documents(
            "Item Group",
            filters=filters or None,
            fields=args.get("fields") or ["name", "item_group_name", "parent_item_group", "is_group"],
            limit=args.get("limit", 100),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "lft asc"),
        )
        return _module_search_result(result, "Item Group", filters, "L0")

    def _stock_create_item_group(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args["data"])
        data["doctype"] = "Item Group"
        result = self.client.create_document("Item Group", data)
        return _stock_master_result(result, doctype="Item Group", action="Created Item Group master record.")

    def _stock_update_item_group(self, args: dict[str, Any]) -> ToolResult:
        result = self.client.update_document("Item Group", args["name"], args["data"])
        return _stock_master_result(result, doctype="Item Group", action="Updated Item Group master record.")

    def _stock_list_uoms(self, args: dict[str, Any]) -> ToolResult:
        filters = dict(args.get("filters") or {})
        if args.get("enabled") is not None:
            filters["enabled"] = args["enabled"]
        if args.get("query"):
            filters["uom_name"] = ["like", f"%{args['query']}%"]
        result = self.client.search_documents(
            "UOM",
            filters=filters or None,
            fields=args.get("fields") or ["name", "uom_name", "enabled"],
            limit=args.get("limit", 100),
            offset=args.get("offset", 0),
            order_by=args.get("order_by", "name asc"),
        )
        return _module_search_result(result, "UOM", filters, "L0")

    def _stock_create_uom(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args["data"])
        data["doctype"] = "UOM"
        result = self.client.create_document("UOM", data)
        return _stock_master_result(result, doctype="UOM", action="Created UOM master record.")

    def _stock_update_uom(self, args: dict[str, Any]) -> ToolResult:
        result = self.client.update_document("UOM", args["name"], args["data"])
        return _stock_master_result(result, doctype="UOM", action="Updated UOM master record.")

    def _stock_submit_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_stock_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if guard:
            return guard
        return self.client.submit_stock_document(args["doctype"], args["name"])

    def _stock_item_code_from_args(self, args: dict[str, Any]) -> str | None:
        if args.get("item_code"):
            return str(args["item_code"])
        if args.get("selected_item_code") and args.get("selection_confirmed"):
            return str(args["selected_item_code"])
        query = args.get("item_query") or args.get("query")
        if not query:
            return None
        result = MaterialSearch(self.client).search_items(
            str(query),
            specs=args.get("specs"),
            item_group=args.get("item_group"),
            enabled_only=True,
            limit=5,
        )
        return _select_ready_item(result)

    def _normalize_stock_item_row(self, item: dict[str, Any]) -> dict[str, Any]:
        row = dict(item)
        if not row.get("item_code"):
            row["item_code"] = self._stock_item_code_from_args(row)
        return row

    def _normalize_pick_list_location(self, item: dict[str, Any]) -> dict[str, Any]:
        row = dict(item)
        if not row.get("item_code"):
            row["item_code"] = self._stock_item_code_from_args(row)
        allowed_fields = {
            "item_code",
            "item_name",
            "warehouse",
            "qty",
            "stock_qty",
            "stock_uom",
            "batch_no",
            "serial_no",
            "sales_order_item",
            "material_request_item",
            "picked_qty",
            "description",
        }
        return _without_empty({field: row.get(field) for field in allowed_fields})

    def _normalize_stock_preview_row(self, item: dict[str, Any]) -> dict[str, Any]:
        row = dict(item)
        if not row.get("item_code"):
            row["item_code"] = self._stock_item_code_from_args(row)
        allowed_fields = {
            "item_code",
            "warehouse",
            "qty",
            "qty_delta",
            "required_qty",
            "incoming_rate",
            "valuation_rate",
            "voucher_type",
            "voucher_no",
            "voucher_detail_no",
        }
        return _without_empty({field: row.get(field) for field in allowed_fields})

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

def _report_filters(args: dict[str, Any]) -> dict[str, Any]:
    filters = dict(args.get("filters") or {})
    for key in ("company", "from_date", "to_date", "fiscal_year", "account", "party_type", "party"):
        if args.get(key) is not None:
            filters[key] = args[key]
    return filters


def _supplier_quotation_comparison_result(
    quotations: list[dict[str, Any]],
    requested_names: list[str],
    *,
    include_drafts: bool,
) -> ToolResult:
    summaries: list[dict[str, Any]] = []
    comparable: list[tuple[dict[str, Any], dict[str, Any]]] = []
    excluded: list[dict[str, Any]] = []
    for doc in quotations:
        summary = _supplier_quotation_summary(doc)
        summaries.append(summary)
        docstatus = summary.get("docstatus")
        if docstatus == 2:
            excluded.append({**summary, "reason": "cancelled"})
            continue
        if docstatus == 0 and not include_drafts:
            excluded.append({**summary, "reason": "draft_not_included"})
            continue
        if docstatus not in (0, 1):
            excluded.append({**summary, "reason": "unsupported_docstatus"})
            continue
        comparable.append((doc, summary))

    if not comparable:
        return ToolResult(
            ok=False,
            error="No comparable Supplier Quotation documents were available.",
            error_type="no_comparable_quotations",
            user_message="没有可比较的供应商报价单。默认只比较已提交报价；如需草稿预览，请设置 include_drafts=true。",
            data={
                "doctype": "Supplier Quotation",
                "status": "no_comparable_quotations",
                "summary": "No submitted Supplier Quotations were available for comparison.",
                "requested_supplier_quotations": requested_names,
                "quotations": summaries,
                "excluded_quotations": excluded,
                "next_actions": ["submit_supplier_quotations", "retry_comparison"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )

    currencies = sorted({summary["currency"] for _, summary in comparable if summary.get("currency")})
    warnings = []
    if len(currencies) > 1:
        warnings.append("Multiple currencies are present; nominal totals are not directly comparable without FX normalization.")
    if include_drafts:
        warnings.append("Draft Supplier Quotations are included for preview only and must be reviewed before award.")

    total_ranking = sorted(
        (_supplier_quotation_ranking_row(summary) for _, summary in comparable),
        key=lambda row: _sort_number(row.get("total_amount")),
    )
    item_comparisons = _supplier_quotation_item_comparisons(comparable)
    lowest = total_ranking[0]
    recommendation_status = "review_required" if len(currencies) > 1 else "lowest_total"
    recommendation = {
        "status": recommendation_status,
        "supplier_quotation": lowest.get("name"),
        "supplier": lowest.get("supplier"),
        "total_amount": lowest.get("total_amount"),
        "currency": lowest.get("currency"),
        "requires_human_review": True,
        "award_tool": None,
        "draft_po_tool": "erpnext.buying.create_purchase_order_draft",
    }
    return ToolResult(
        ok=True,
        data={
            "doctype": "Supplier Quotation",
            "status": "Comparison Ready",
            "summary": f"Compared {len(comparable)} Supplier Quotations; lowest comparable total is {lowest.get('name')}.",
            "requested_supplier_quotations": requested_names,
            "include_drafts": include_drafts,
            "quotations": summaries,
            "excluded_quotations": excluded,
            "total_ranking": total_ranking,
            "item_comparisons": item_comparisons,
            "recommendation": recommendation,
            "warnings": warnings,
            "next_actions": ["review_price_quality_terms", "create_purchase_order_draft"],
            "risk": {"level": "L1", "requires_confirmation_for_submit": False, "does_not_award": True},
        },
        debug={"raw_supplier_quotation_names": [doc.get("name") for doc in quotations]},
    )


def _supplier_quotation_summary(doc: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in doc.get("items") or [] if isinstance(item, dict)]
    total_amount = _first_float(doc, ("grand_total", "rounded_total", "net_total", "total"))
    if total_amount is None:
        total_amount = sum(_supplier_quotation_item_amount(item) for item in items)
    return {
        "name": doc.get("name"),
        "supplier": doc.get("supplier"),
        "supplier_name": doc.get("supplier_name"),
        "transaction_date": doc.get("transaction_date"),
        "valid_till": doc.get("valid_till"),
        "currency": doc.get("currency"),
        "docstatus": doc.get("docstatus"),
        "status": doc.get("status"),
        "request_for_quotation": doc.get("request_for_quotation"),
        "item_count": len(items),
        "total_amount": round(float(total_amount or 0), 2),
    }


def _supplier_quotation_ranking_row(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": summary.get("name"),
        "supplier": summary.get("supplier"),
        "supplier_name": summary.get("supplier_name"),
        "docstatus": summary.get("docstatus"),
        "currency": summary.get("currency"),
        "total_amount": summary.get("total_amount"),
        "item_count": summary.get("item_count"),
    }


def _supplier_quotation_item_comparisons(comparable: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for doc, summary in comparable:
        for index, item in enumerate(doc.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            item_key = str(item.get("item_code") or item.get("item_name") or f"{summary.get('name')}:line-{index}")
            bucket = buckets.setdefault(
                item_key,
                {
                    "item_code": item.get("item_code"),
                    "item_name": item.get("item_name"),
                    "uom": item.get("uom"),
                    "offers": [],
                },
            )
            bucket["offers"].append(_supplier_quotation_item_offer(item, summary))

    comparisons: list[dict[str, Any]] = []
    for item_key, bucket in buckets.items():
        offers = sorted(bucket["offers"], key=lambda offer: (_sort_number(offer.get("rate")), _sort_number(offer.get("amount"))))
        if not offers:
            continue
        best = offers[0]
        comparisons.append(
            {
                "item_code": bucket.get("item_code") or item_key,
                "item_name": bucket.get("item_name"),
                "uom": bucket.get("uom"),
                "offer_count": len(offers),
                "best_supplier_quotation": best.get("supplier_quotation"),
                "best_supplier": best.get("supplier"),
                "best_rate": best.get("rate"),
                "best_amount": best.get("amount"),
                "offers": offers,
            }
        )
    return sorted(comparisons, key=lambda row: str(row.get("item_code") or ""))


def _supplier_quotation_item_offer(item: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    qty = _float_or_none(item.get("qty"))
    rate = _supplier_quotation_item_rate(item)
    amount = _supplier_quotation_item_amount(item)
    return {
        "supplier_quotation": summary.get("name"),
        "supplier": summary.get("supplier"),
        "supplier_name": summary.get("supplier_name"),
        "docstatus": summary.get("docstatus"),
        "currency": summary.get("currency"),
        "qty": qty,
        "rate": round(rate, 6) if rate is not None else None,
        "amount": round(amount, 2),
    }


def _supplier_quotation_item_rate(item: dict[str, Any]) -> float | None:
    return _first_float(item, ("rate", "net_rate", "base_rate", "price_list_rate"))


def _supplier_quotation_item_amount(item: dict[str, Any]) -> float:
    amount = _first_float(item, ("amount", "net_amount", "base_net_amount", "base_amount"))
    if amount is not None:
        return amount
    qty = _float_or_none(item.get("qty")) or 0.0
    rate = _supplier_quotation_item_rate(item) or 0.0
    return qty * rate


def _first_float(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _float_or_none(data.get(key))
        if value is not None:
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sort_number(value: Any) -> float:
    numeric = _float_or_none(value)
    if numeric is None:
        return float("inf")
    return numeric


def _validate_accounting_report_filters(report_name: str, filters: dict[str, Any]) -> ToolResult | None:
    spec = _accounting_report_filter_spec(report_name)
    required = spec["required_filters"] if spec else []
    missing = [field for field in required if not filters.get(field)]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Missing required report filters for {report_name}: {', '.join(missing)}",
            error_type="missing_report_filter",
            user_message=f"{report_name} 报表缺少必要过滤条件：{', '.join(missing)}。",
            data={
                "report_name": report_name,
                "status": "Missing Required Filters",
                "missing_filters": missing,
                "summary": f"{report_name} requires {', '.join(required)} before running.",
                "next_actions": ["provide_required_filters", "retry_report"],
                "risk": {"level": "L0"},
            },
        )

    date_guard = _validate_report_date_range(report_name, filters)
    if date_guard:
        return date_guard
    return None


def _accounting_report_filter_spec(report_name: str) -> dict[str, Any] | None:
    specs: dict[str, dict[str, Any]] = {
        "General Ledger": {
            "required_filters": ["company"],
            "optional_filters": ["from_date", "to_date", "account", "party_type", "party", "voucher_no", "cost_center", "project"],
            "defaults": {"group_by": "Group by Voucher (Consolidated)"},
            "known_date_filters": ["from_date", "to_date"],
        },
        "Accounts Receivable": {
            "required_filters": ["company"],
            "optional_filters": ["report_date", "customer", "customer_group", "payment_terms_template", "sales_partner", "based_on_payment_terms"],
            "defaults": {},
            "known_date_filters": ["report_date"],
        },
        "Accounts Payable": {
            "required_filters": ["company"],
            "optional_filters": ["report_date", "supplier", "supplier_group", "payment_terms_template", "based_on_payment_terms"],
            "defaults": {},
            "known_date_filters": ["report_date"],
        },
        "Trial Balance": {
            "required_filters": ["company"],
            "optional_filters": ["from_date", "to_date", "fiscal_year", "finance_book", "cost_center", "project"],
            "defaults": {},
            "known_date_filters": ["from_date", "to_date"],
        },
        "Balance Sheet": {
            "required_filters": ["company"],
            "optional_filters": ["period_start_date", "period_end_date", "from_fiscal_year", "to_fiscal_year", "periodicity", "finance_book"],
            "defaults": {"periodicity": "Yearly"},
            "known_date_filters": ["period_start_date", "period_end_date"],
        },
        "Profit and Loss Statement": {
            "required_filters": ["company"],
            "optional_filters": ["period_start_date", "period_end_date", "from_fiscal_year", "to_fiscal_year", "periodicity", "finance_book", "cost_center", "project"],
            "defaults": {"periodicity": "Yearly"},
            "known_date_filters": ["period_start_date", "period_end_date"],
        },
        "Cash Flow": {
            "required_filters": ["company"],
            "optional_filters": ["period_start_date", "period_end_date", "from_fiscal_year", "to_fiscal_year", "periodicity", "finance_book"],
            "defaults": {"periodicity": "Yearly"},
            "known_date_filters": ["period_start_date", "period_end_date"],
        },
    }
    return specs.get(report_name)


def _validate_report_date_range(report_name: str, filters: dict[str, Any]) -> ToolResult | None:
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not from_date and not to_date:
        return None
    parsed: dict[str, date] = {}
    for key, value in {"from_date": from_date, "to_date": to_date}.items():
        if not value:
            continue
        try:
            parsed[key] = date.fromisoformat(str(value))
        except ValueError:
            return ToolResult(
                ok=False,
                error=f"Invalid date filter for {report_name}: {key}={value}",
                error_type="validation_error",
                user_message=f"{report_name} 报表的 {key} 必须使用 YYYY-MM-DD 日期格式。",
                data={
                    "report_name": report_name,
                    "status": "Invalid Date Filter",
                    "invalid_filter": key,
                    "summary": f"{key} must be an ISO date in YYYY-MM-DD format.",
                    "next_actions": ["fix_date_filter", "retry_report"],
                    "risk": {"level": "L0"},
                },
            )
    if parsed.get("from_date") and parsed.get("to_date") and parsed["from_date"] > parsed["to_date"]:
        return ToolResult(
            ok=False,
            error=f"Invalid date range for {report_name}: from_date is after to_date.",
            error_type="validation_error",
            user_message=f"{report_name} 报表的 from_date 不能晚于 to_date。",
            data={
                "report_name": report_name,
                "status": "Invalid Date Range",
                "summary": "from_date must be earlier than or equal to to_date.",
                "next_actions": ["fix_date_range", "retry_report"],
                "risk": {"level": "L0"},
            },
        )
    return None


def _draft_doc(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
    draft = dict(data)
    draft["doctype"] = doctype
    draft["docstatus"] = 0
    return draft


def _asset_financial_snapshot(
    asset: dict[str, Any],
    schedule_docs: list[dict[str, Any]],
    *,
    finance_book: str | None,
    include_schedule_rows: bool,
) -> dict[str, Any]:
    finance_books = [
        row
        for row in asset.get("finance_books") or []
        if isinstance(row, dict) and (not finance_book or row.get("finance_book") == finance_book)
    ]
    schedules = []
    for schedule in schedule_docs:
        rows = [
            _clean_mapping(
                {
                    "schedule_date": row.get("schedule_date"),
                    "depreciation_amount": row.get("depreciation_amount"),
                    "accumulated_depreciation_amount": row.get("accumulated_depreciation_amount"),
                    "journal_entry": row.get("journal_entry"),
                    "depreciation_status": row.get("depreciation_status"),
                }
            )
            for row in schedule.get("depreciation_schedule") or []
            if isinstance(row, dict)
        ]
        schedules.append(
            _clean_mapping(
                {
                    "name": schedule.get("name"),
                    "asset": schedule.get("asset"),
                    "finance_book": schedule.get("finance_book"),
                    "status": schedule.get("status"),
                    "docstatus": schedule.get("docstatus"),
                    "value_after_depreciation": schedule.get("value_after_depreciation"),
                    "schedule_row_count": len(rows),
                    "schedule_rows": rows if include_schedule_rows else None,
                }
            )
        )

    return {
        "doctype": "Asset",
        "name": asset.get("name"),
        "docstatus": asset.get("docstatus"),
        "status": "Financial Snapshot",
        "summary": f"Prepared read-only financial snapshot for Asset {asset.get('name')}.",
        "asset": _clean_mapping(
            {
                "asset_name": asset.get("asset_name"),
                "company": asset.get("company"),
                "item_code": asset.get("item_code"),
                "asset_category": asset.get("asset_category"),
                "location": asset.get("location"),
                "custodian": asset.get("custodian"),
                "asset_status": asset.get("status"),
                "available_for_use_date": asset.get("available_for_use_date"),
                "gross_purchase_amount": asset.get("gross_purchase_amount"),
                "purchase_amount": asset.get("purchase_amount"),
                "opening_accumulated_depreciation": asset.get("opening_accumulated_depreciation"),
                "value_after_depreciation": asset.get("value_after_depreciation"),
                "total_number_of_depreciations": asset.get("total_number_of_depreciations"),
                "frequency_of_depreciation": asset.get("frequency_of_depreciation"),
                "depreciation_method": asset.get("depreciation_method"),
            }
        ),
        "finance_book_filter": finance_book,
        "finance_books": finance_books,
        "depreciation_schedules": schedules,
        "next_actions": ["review_financial_snapshot", "prepare_disposal_or_sale", "create_value_adjustment_draft"],
        "risk": {
            "level": "L0",
            "creates_financial_posting": False,
            "does_not_process_depreciation": True,
            "does_not_create_disposal_or_sale": True,
        },
    }


def _asset_depreciation_schedule_preview(schedule: dict[str, Any], only_due_before: str | None) -> dict[str, Any]:
    rows = []
    for row in schedule.get("depreciation_schedule") or []:
        if not isinstance(row, dict):
            continue
        schedule_date = row.get("schedule_date")
        if only_due_before and schedule_date and not _iso_date_on_or_before(str(schedule_date), only_due_before):
            continue
        rows.append(
            _clean_mapping(
                {
                    "schedule_date": schedule_date,
                    "depreciation_amount": row.get("depreciation_amount"),
                    "accumulated_depreciation_amount": row.get("accumulated_depreciation_amount"),
                    "journal_entry": row.get("journal_entry"),
                    "depreciation_status": row.get("depreciation_status"),
                }
            )
        )
    return _clean_mapping(
        {
            "name": schedule.get("name"),
            "asset": schedule.get("asset"),
            "finance_book": schedule.get("finance_book"),
            "status": schedule.get("status"),
            "docstatus": schedule.get("docstatus"),
            "value_after_depreciation": schedule.get("value_after_depreciation"),
            "schedule_row_count": len(rows),
            "schedule_rows": rows,
        }
    )


def _supplier_procurement_eligibility(supplier: dict[str, Any], scorecards: list[Any]) -> dict[str, Any]:
    scorecard_rows = [row for row in scorecards if isinstance(row, dict)]
    rfq_blockers = _supplier_blockers(supplier, scorecard_rows, "rfq")
    po_blockers = _supplier_blockers(supplier, scorecard_rows, "po")
    rfq_warnings = _supplier_warnings(supplier, scorecard_rows, "rfq")
    po_warnings = _supplier_warnings(supplier, scorecard_rows, "po")
    return {
        "eligible_for_rfq": _procurement_eligibility_status(rfq_blockers, rfq_warnings, scorecard_rows),
        "eligible_for_po": _procurement_eligibility_status(po_blockers, po_warnings, scorecard_rows),
        "rfq_blockers": rfq_blockers,
        "po_blockers": po_blockers,
        "rfq_warnings": rfq_warnings,
        "po_warnings": po_warnings,
        "scorecard_status": "available" if scorecard_rows else "unknown",
    }


def _supplier_blockers(supplier: dict[str, Any], scorecards: list[dict[str, Any]], mode: str) -> list[str]:
    blockers = []
    for field in ("disabled", "is_frozen", "on_hold"):
        if _truthy(supplier.get(field)):
            blockers.append(field)
    flag = "prevent_rfqs" if mode == "rfq" else "prevent_pos"
    if _truthy(supplier.get(flag)):
        blockers.append(flag)
    if any(_truthy(row.get(flag)) for row in scorecards):
        blockers.append(f"scorecard_{flag}")
    return blockers


def _supplier_warnings(supplier: dict[str, Any], scorecards: list[dict[str, Any]], mode: str) -> list[str]:
    flag = "warn_rfqs" if mode == "rfq" else "warn_pos"
    warnings = []
    if _truthy(supplier.get(flag)):
        warnings.append(flag)
    if any(_truthy(row.get(flag)) for row in scorecards):
        warnings.append(f"scorecard_{flag}")
    return warnings


def _procurement_eligibility_status(blockers: list[str], warnings: list[str], scorecards: list[dict[str, Any]]) -> str:
    if blockers:
        return "blocked"
    if warnings:
        return "warning"
    if not scorecards:
        return "unknown"
    return "allowed"


def _stock_batch_balance_rows(
    item_code: str,
    batch_meta: dict[str, dict[str, Any]],
    ledger_rows: list[Any],
    *,
    include_expired: bool,
    include_zero: bool,
    as_of_date: str | None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in ledger_rows:
        if not isinstance(row, dict):
            continue
        batch_no = row.get("batch_no")
        if not batch_no:
            continue
        batch_key = str(batch_no)
        meta = batch_meta.get(batch_key, {})
        if not include_expired and _batch_is_expired(meta, as_of_date):
            continue
        key = (batch_key, row.get("warehouse"))
        existing = grouped.setdefault(
            key,
            {
                "item_code": item_code,
                "batch_no": batch_key,
                "warehouse": row.get("warehouse"),
                "actual_qty": 0.0,
                "latest_posting_date": row.get("posting_date"),
                "latest_posting_time": row.get("posting_time"),
                "latest_qty_after_transaction": row.get("qty_after_transaction"),
                "valuation_rate": row.get("valuation_rate"),
                "stock_value": row.get("stock_value"),
                "expiry_date": meta.get("expiry_date"),
                "disabled": _truthy(meta.get("disabled")),
            },
        )
        existing["actual_qty"] += _float_or_none(row.get("actual_qty")) or 0.0

    records = []
    for record in grouped.values():
        record["actual_qty"] = round(record["actual_qty"], 6)
        if not include_zero and record["actual_qty"] == 0:
            continue
        records.append(record)
    return sorted(records, key=lambda row: (str(row.get("expiry_date") or "9999-12-31"), str(row.get("batch_no") or ""), str(row.get("warehouse") or "")))


def _batch_is_expired(batch: dict[str, Any], as_of_date: str | None) -> bool:
    expiry = batch.get("expiry_date")
    if not expiry:
        return False
    comparison = as_of_date or date.today().isoformat()
    return _iso_date_on_or_before(str(expiry), comparison) and str(expiry) < comparison


def _iso_date_on_or_before(candidate: str, boundary: str) -> bool:
    try:
        return date.fromisoformat(candidate) <= date.fromisoformat(boundary)
    except ValueError:
        return candidate <= boundary


def _invoice_doctype_for_payment(party_type: str, payment_type: str) -> str:
    if party_type == "Customer" or payment_type == "Receive":
        return "Sales Invoice"
    if party_type == "Supplier" or payment_type == "Pay":
        return "Purchase Invoice"
    return ""


def _payment_references(
    invoices: list[dict[str, Any]],
    paid_amount: float | int | None,
    allocations: dict[str, Any],
    invoice_doctype: str,
) -> tuple[list[dict[str, Any]], float | None]:
    remaining = float(paid_amount) if paid_amount is not None else None
    references = []
    for invoice in invoices:
        name = invoice.get("name")
        outstanding = float(invoice.get("outstanding_amount") or 0)
        explicit = allocations.get(name) if name else None
        if explicit is not None:
            allocated = min(float(explicit), outstanding)
        elif remaining is None:
            allocated = outstanding
        else:
            allocated = min(max(remaining, 0), outstanding)
        if remaining is not None:
            remaining -= allocated
        references.append(
            {
                "reference_doctype": invoice_doctype,
                "reference_name": name,
                "total_amount": invoice.get("grand_total"),
                "outstanding_amount": outstanding,
                "allocated_amount": allocated,
                "due_date": invoice.get("due_date"),
                "currency": invoice.get("currency"),
            }
        )
    return references, remaining


def _tax_template_doctype(invoice_type: str) -> str | None:
    normalized = invoice_type.lower()
    if normalized in {"sales", "sales_invoice", "sales invoice"}:
        return "Sales Taxes and Charges Template"
    if normalized in {"purchase", "purchase_invoice", "purchase invoice"}:
        return "Purchase Taxes and Charges Template"
    return None


def _prepared_tax_rows(source_taxes: list[dict[str, Any]], net_total: float) -> tuple[list[dict[str, Any]], float]:
    rows = []
    total_tax = 0.0
    for row in source_taxes:
        rate = float(row.get("rate") or 0)
        explicit_amount = row.get("tax_amount") if row.get("tax_amount") is not None else row.get("amount")
        estimated_amount = float(explicit_amount) if explicit_amount is not None else round(net_total * rate / 100, 2)
        total_tax += estimated_amount
        rows.append(
            {
                "charge_type": row.get("charge_type"),
                "account_head": row.get("account_head"),
                "description": row.get("description"),
                "rate": rate,
                "estimated_tax_amount": estimated_amount,
                "cost_center": row.get("cost_center"),
                "included_in_print_rate": row.get("included_in_print_rate"),
            }
        )
    return rows, round(total_tax, 2)


def _users_filters(args: dict[str, Any], keys: tuple[str, ...]) -> list[list[Any]]:
    filters = []
    for key in keys:
        if key in args and args[key] is not None:
            value = args[key]
            if isinstance(value, bool):
                value = 1 if value else 0
            filters.append([key, "=", value])
    return filters


def _extract_permission_rows(schema_data: dict[str, Any]) -> list[dict[str, Any]]:
    containers = [schema_data]
    data = schema_data.get("data")
    if isinstance(data, dict):
        containers.append(data)
    docs = schema_data.get("docs")
    if isinstance(docs, list):
        containers.extend(doc for doc in docs if isinstance(doc, dict))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for container in containers:
        raw_permissions = container.get("permissions")
        if not isinstance(raw_permissions, list):
            continue
        for row in raw_permissions:
            if not isinstance(row, dict):
                continue
            fingerprint = tuple(sorted((str(key), str(value)) for key, value in row.items()))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append(dict(row))
    return rows


def _metadata_effective_permissions(
    role_names: set[str],
    permission_rows: list[dict[str, Any]],
) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    effective = {action: False for action in USER_PERMISSION_ACTIONS}
    matched_rows: list[dict[str, Any]] = []
    roles_to_match = set(role_names) | {"All"}

    for row in permission_rows:
        role = row.get("role")
        if role not in roles_to_match:
            continue
        matched_row = _permission_row_preview(row)
        matched_rows.append(matched_row)
        for action in USER_PERMISSION_ACTIONS:
            if _truthy(row.get(action)):
                effective[action] = True
    return effective, matched_rows


def _permission_difference_reasons(docname: str | None, metadata_allowed: bool, server_allowed: bool) -> list[str]:
    if metadata_allowed == server_allowed:
        return []
    if metadata_allowed and not server_allowed:
        reasons = ["user_permission", "controller_hook", "workflow_state"]
        if docname:
            reasons.insert(0, "owner_rule")
            reasons.insert(1, "docshare")
        return reasons
    return ["docshare", "owner_rule", "controller_hook"]


def _permission_row_preview(row: dict[str, Any]) -> dict[str, Any]:
    preview = {
        "role": row.get("role"),
        "permlevel": row.get("permlevel", 0),
        "if_owner": _truthy(row.get("if_owner")),
        "apply_user_permissions": _truthy(row.get("apply_user_permissions")),
    }
    for action in USER_PERMISSION_ACTIONS:
        preview[action] = _truthy(row.get(action))
    if row.get("name"):
        preview["name"] = row.get("name")
    return preview


PERMISSION_POLICY_FIELDS = set(USER_PERMISSION_ACTIONS) | {"if_owner", "apply_user_permissions"}
PERMISSION_POLICY_MATCH_FIELDS = PERMISSION_POLICY_FIELDS | {"name", "role", "permlevel"}


def _simulate_permission_policy_changes(
    before_rows: list[dict[str, Any]],
    changes: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]] | ToolResult:
    after_rows = [dict(row) for row in before_rows]
    diff: dict[str, list[dict[str, Any]]] = {"added": [], "updated": [], "removed": []}
    normalized_changes: list[dict[str, Any]] = []

    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            return _permission_policy_validation_error(index, "Each change must be an object.")
        operation = str(change.get("operation") or "").strip().lower()
        if operation not in {"add", "update", "remove"}:
            return _permission_policy_validation_error(index, "operation must be add, update, or remove.")

        permissions_result = _normalize_permission_policy_permissions(change.get("permissions") or {}, index)
        if isinstance(permissions_result, ToolResult):
            return permissions_result
        permissions = permissions_result

        if operation == "add":
            role = change.get("role")
            if not role:
                return _permission_policy_validation_error(index, "add requires role.")
            permlevel_result = _normalize_permlevel(change.get("permlevel", 0), index)
            if isinstance(permlevel_result, ToolResult):
                return permlevel_result
            row = _blank_permission_policy_row(str(role), permlevel_result)
            row.update(permissions)
            after_rows.append(row)
            diff["added"].append(dict(row))
            normalized_changes.append({"operation": operation, "role": row["role"], "permlevel": row["permlevel"], "permissions": permissions})
            continue

        match_result = _normalize_permission_policy_match(change.get("match") or change, index)
        if isinstance(match_result, ToolResult):
            return match_result
        match = match_result
        target_indexes = [row_index for row_index, row in enumerate(after_rows) if _permission_policy_row_matches(row, match)]
        if not target_indexes:
            return _permission_policy_validation_error(index, "No permission row matched the change.", {"match": match})
        if len(target_indexes) > 1:
            return _permission_policy_validation_error(index, "Permission row match is ambiguous.", {"match": match, "matched_rows": [after_rows[i] for i in target_indexes]})

        target_index = target_indexes[0]
        before = dict(after_rows[target_index])
        if operation == "remove":
            removed = after_rows.pop(target_index)
            diff["removed"].append(dict(removed))
            normalized_changes.append({"operation": operation, "match": match})
            continue

        if not permissions:
            return _permission_policy_validation_error(index, "update requires at least one permission field.")
        updated = dict(before)
        updated.update(permissions)
        after_rows[target_index] = updated
        changed_fields = {
            key: {"before": before.get(key), "after": updated.get(key)}
            for key in permissions
            if before.get(key) != updated.get(key)
        }
        diff["updated"].append({"match": match, "before": before, "after": dict(updated), "changed_fields": changed_fields})
        normalized_changes.append({"operation": operation, "match": match, "permissions": permissions})

    return after_rows, diff, normalized_changes


def _blank_permission_policy_row(role: str, permlevel: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "role": role,
        "permlevel": permlevel,
        "if_owner": False,
        "apply_user_permissions": False,
    }
    for action in USER_PERMISSION_ACTIONS:
        row[action] = False
    return row


def _normalize_permission_policy_permissions(value: dict[str, Any], index: int) -> dict[str, bool] | ToolResult:
    if not isinstance(value, dict):
        return _permission_policy_validation_error(index, "permissions must be an object.")
    invalid = sorted(set(value) - PERMISSION_POLICY_FIELDS)
    if invalid:
        return _permission_policy_validation_error(index, "Unsupported permission fields.", {"unsupported_fields": invalid, "supported_fields": sorted(PERMISSION_POLICY_FIELDS)})
    return {key: _truthy(field_value) for key, field_value in value.items()}


def _normalize_permission_policy_match(value: dict[str, Any], index: int) -> dict[str, Any] | ToolResult:
    if not isinstance(value, dict):
        return _permission_policy_validation_error(index, "match must be an object.")
    match = {key: value[key] for key in value if key in PERMISSION_POLICY_MATCH_FIELDS and key not in {"operation", "permissions"}}
    invalid = sorted(set(value) - PERMISSION_POLICY_MATCH_FIELDS - {"operation", "permissions"})
    if invalid:
        return _permission_policy_validation_error(index, "Unsupported match fields.", {"unsupported_fields": invalid, "supported_fields": sorted(PERMISSION_POLICY_MATCH_FIELDS)})
    if not match:
        return _permission_policy_validation_error(index, "update/remove requires match, role, permlevel, or name.")
    if "permlevel" in match:
        permlevel_result = _normalize_permlevel(match["permlevel"], index)
        if isinstance(permlevel_result, ToolResult):
            return permlevel_result
        match["permlevel"] = permlevel_result
    for key in PERMISSION_POLICY_FIELDS:
        if key in match:
            match[key] = _truthy(match[key])
    if "role" in match:
        match["role"] = str(match["role"])
    if "name" in match:
        match["name"] = str(match["name"])
    return match


def _permission_policy_row_matches(row: dict[str, Any], match: dict[str, Any]) -> bool:
    return all(row.get(key) == value for key, value in match.items())


def _normalize_permlevel(value: Any, index: int) -> int | ToolResult:
    try:
        permlevel = int(value)
    except (TypeError, ValueError):
        return _permission_policy_validation_error(index, "permlevel must be an integer.")
    if permlevel < 0:
        return _permission_policy_validation_error(index, "permlevel must be zero or greater.")
    return permlevel


def _permission_policy_validation_error(index: int, message: str, data: dict[str, Any] | None = None) -> ToolResult:
    payload = {"change_index": index, "message": message}
    if data:
        payload.update(data)
    return ToolResult(
        ok=False,
        error=message,
        error_type="validation_error",
        user_message="权限策略预览参数不正确，请检查变更类型、匹配条件和权限字段。",
        data=payload,
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    return bool(value)


def _users_read_result(result: ToolResult, doctype: str, summary: str) -> ToolResult:
    if not result.ok:
        return result
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": doctype,
            "status": "Read Only",
            "summary": summary,
            "records": result.data or [],
            "next_actions": ["review_results", "use_L5_ADMIN_tool_for_changes"],
            "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
        },
    )


def _users_write_result(result: ToolResult, doctype: str, name: str | None, summary: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": doctype,
            "name": raw.get("name") or name,
            "docstatus": raw.get("docstatus"),
            "status": "Admin Change Applied",
            "summary": summary,
            "next_actions": ["audit_change", "review_effective_access"],
            "risk": {"level": "L5_ADMIN", "confirmation_required": True, "confirmation_checked": True},
        },
        debug={"raw_document": raw or result.data},
    )


def _buying_quotation_comparison_result(
    quotations: list[dict[str, Any]],
    *,
    prefer: str,
    include_unsubmitted: bool,
) -> ToolResult:
    warnings: list[str] = []
    rows_by_item: dict[str, list[dict[str, Any]]] = {}
    skipped: list[dict[str, Any]] = []

    for quotation in quotations:
        name = quotation.get("name")
        docstatus = int(quotation.get("docstatus") or 0)
        if docstatus == 0 and not include_unsubmitted:
            skipped.append({"supplier_quotation": name, "reason": "draft_excluded"})
            continue
        supplier = quotation.get("supplier")
        currency = quotation.get("currency")
        transaction_date = quotation.get("transaction_date")
        valid_till = quotation.get("valid_till")
        for item in quotation.get("items") or []:
            if not isinstance(item, dict):
                continue
            item_code = item.get("item_code")
            if not item_code:
                warnings.append(f"Supplier Quotation {name} has an item row without item_code.")
                continue
            qty = _number_or_none(item.get("qty"))
            rate = _number_or_none(item.get("rate") if item.get("rate") is not None else item.get("base_rate"))
            amount = _number_or_none(item.get("amount") if item.get("amount") is not None else item.get("base_amount"))
            row = {
                "supplier_quotation": name,
                "supplier": supplier,
                "docstatus": docstatus,
                "currency": currency,
                "transaction_date": transaction_date,
                "valid_till": valid_till,
                "item_code": item_code,
                "item_name": item.get("item_name"),
                "qty": qty,
                "uom": item.get("uom") or item.get("stock_uom"),
                "rate": rate,
                "amount": amount,
                "schedule_date": item.get("schedule_date") or item.get("expected_delivery_date"),
                "lead_time_days": _number_or_none(item.get("lead_time_days")),
            }
            rows_by_item.setdefault(str(item_code), []).append(row)

    comparisons = []
    recommendations = []
    for item_code in sorted(rows_by_item):
        candidates = rows_by_item[item_code]
        currencies = {row.get("currency") for row in candidates if row.get("currency")}
        if len(currencies) > 1:
            warnings.append(f"Item {item_code} has multiple currencies; rates were not FX-normalized.")
        ranked = sorted(candidates, key=_quotation_candidate_sort_key(prefer))
        best = ranked[0] if ranked else None
        comparisons.append(
            {
                "item_code": item_code,
                "candidate_count": len(candidates),
                "candidates": ranked,
                "best_supplier": best.get("supplier") if best else None,
                "best_supplier_quotation": best.get("supplier_quotation") if best else None,
                "best_rate": best.get("rate") if best else None,
                "currency": best.get("currency") if best else None,
            }
        )
        if best:
            recommendations.append(
                {
                    "item_code": item_code,
                    "supplier": best.get("supplier"),
                    "supplier_quotation": best.get("supplier_quotation"),
                    "rate": best.get("rate"),
                    "currency": best.get("currency"),
                    "reason": _quotation_recommendation_reason(best, prefer),
                }
            )

    return ToolResult(
        ok=True,
        data={
            "doctype": "Supplier Quotation",
            "name": None,
            "docstatus": None,
            "status": "Comparison Preview",
            "summary": f"Compared {len(quotations)} supplier quotation(s) across {len(comparisons)} item(s).",
            "next_actions": ["review_recommendations", "confirm_supplier_selection", "create_purchase_order_draft"],
            "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            "prefer": prefer,
            "comparisons": comparisons,
            "recommendations": recommendations,
            "warnings": warnings,
            "skipped": skipped,
        },
        debug={"raw_documents": quotations},
    )


def _quotation_candidate_sort_key(prefer: str) -> Callable[[dict[str, Any]], tuple[Any, ...]]:
    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        rate = row.get("rate")
        amount = row.get("amount")
        schedule_date = row.get("schedule_date") or "9999-12-31"
        lead_time = row.get("lead_time_days")
        rate_key = rate if rate is not None else float("inf")
        amount_key = amount if amount is not None else float("inf")
        lead_time_key = lead_time if lead_time is not None else float("inf")
        if prefer == "earliest_delivery":
            return (schedule_date, lead_time_key, rate_key, amount_key, str(row.get("supplier") or ""))
        if prefer == "lowest_amount":
            return (amount_key, rate_key, schedule_date, str(row.get("supplier") or ""))
        return (rate_key, amount_key, schedule_date, str(row.get("supplier") or ""))

    return key


def _quotation_recommendation_reason(row: dict[str, Any], prefer: str) -> str:
    if prefer == "earliest_delivery":
        return "Earliest schedule date, then lead time and rate."
    if prefer == "lowest_amount":
        return "Lowest line amount, then rate and delivery date."
    return "Lowest quoted rate, then amount and delivery date."


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _require_admin_confirmation(
    action: str,
    doctype: str,
    name: str | None,
    confirmation: dict[str, Any] | None,
    preview: dict[str, Any],
) -> ToolResult | None:
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed", "confirmed_by", "confirmed_at", "reason")
        if not confirmation.get(field)
    ]
    if confirmation.get("confirmed") is not True or missing:
        return ToolResult(
            ok=False,
            data={
                "doctype": doctype,
                "name": name,
                "status": "Confirmation Required",
                "summary": f"Admin confirmation required before {action} can be executed.",
                "preview": preview,
                "next_actions": ["obtain_explicit_admin_confirmation", "retry_with_confirmation_metadata"],
                "risk": {
                    "level": "L5_ADMIN",
                    "confirmation_required": True,
                    "required_confirmation_fields": ["confirmed", "confirmed_by", "confirmed_at", "reason"],
                },
            },
            error=f"Admin confirmation required for {action}.",
            error_type="admin_confirmation_required",
            user_message="用户、角色、权限变更属于 L5_ADMIN 高风险操作，需要明确确认后才能执行。",
            meta={
                "risk_level": "L5_ADMIN",
                "required_confirmation_fields": ["confirmed", "confirmed_by", "confirmed_at", "reason"],
                "action": action,
                "doctype": doctype,
                "name": name,
            },
        )
    return None


def _clean_mapping(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _module_search_result(result: ToolResult, doctype: str, filters: dict[str, Any], risk_level: str) -> ToolResult:
    if not result.ok:
        return result
    records = result.data if isinstance(result.data, list) else []
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": doctype,
            "records": records,
            "count": len(records),
            "filters": filters,
            "summary": f"Fetched {len(records)} {doctype} records.",
            "next_actions": [],
            "risk": {"level": risk_level},
        },
        debug={"raw_data": result.data},
    )


def _module_report_result(result: ToolResult, report_name: str, filters: dict[str, Any]) -> ToolResult:
    if not result.ok:
        return result
    data = result.data if isinstance(result.data, dict) else {}
    rows = data.get("rows") or []
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "report_name": report_name,
            "filters": filters,
            "columns": data.get("columns") or [],
            "rows": rows,
            "summary": f"Fetched {len(rows)} rows from {report_name}.",
            "report_summary": data.get("summary"),
            "next_actions": [],
            "risk": {"level": "L0"},
        },
        debug={"raw_report": data.get("raw") or data},
    )


def _module_doc_result(
    result: ToolResult,
    doctype: str,
    risk_level: str,
    summary: str,
    next_actions: list[str],
    *,
    requires_confirmation_for_submit: bool,
) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    docstatus = raw.get("docstatus")
    status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(docstatus, raw.get("status"))
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data={
            "doctype": raw.get("doctype") or doctype,
            "name": raw.get("name"),
            "docstatus": docstatus,
            "status": status,
            "summary": summary,
            "next_actions": next_actions,
            "risk": {
                "level": risk_level,
                "requires_confirmation_for_submit": requires_confirmation_for_submit,
            },
        },
        debug={"raw_document": result.data},
    )


def _module_draft_result(
    result: ToolResult,
    *,
    doctype: str,
    summary: str,
    risk_level: str = "L3",
    submit_tool: str | None = None,
) -> ToolResult:
    wrapped = _module_doc_result(
        result,
        doctype,
        risk_level,
        summary,
        ["review_draft", "confirm_submit"] if submit_tool else ["review_master_data"],
        requires_confirmation_for_submit=bool(submit_tool),
    )
    if wrapped.ok and submit_tool and isinstance(wrapped.data, dict):
        wrapped.data["risk"]["submit_tool"] = submit_tool
    return wrapped


def _without_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in (None, "")}


def _select_ready_item(search_result: dict[str, Any]) -> str | None:
    candidates = search_result.get("candidates") or []
    if search_result.get("status") != "ready" or not candidates:
        return None
    candidate = candidates[0]
    if not candidate.get("enabled", True):
        return None
    return candidate.get("item_code")


def _item_resolution_error(message: str = "无法解析到唯一可用的 ERPNext Item，请先调用 erpnext.stock.resolve_item 并让用户确认。") -> ToolResult:
    return ToolResult(
        ok=False,
        error=message,
        error_type="item_resolution_required",
        user_message="无法确认唯一物料编码，请先检索并确认 Item。",
        data={
            "status": "needs_item_resolution",
            "summary": message,
            "next_actions": ["search_items", "confirm_item_selection", "retry_draft_creation"],
            "risk": {"level": "L1", "requires_confirmation_for_submit": False},
        },
        meta={"next_tool": "erpnext.search_items"},
    )


def _stock_draft_result(result: ToolResult, *, doctype: str, summary: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    name = raw.get("name")
    data = {
        "doctype": doctype,
        "name": name,
        "docstatus": raw.get("docstatus", 0),
        "status": "Draft",
        "summary": summary,
        "next_actions": ["review_draft", "confirm_submit"],
        "risk": {
            "level": "L3",
            "requires_confirmation_for_submit": True,
            "submit_tool": "erpnext.stock.submit_document",
        },
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug={"raw_document": raw} if raw else result.debug,
    )


def _stock_master_result(result: ToolResult, *, doctype: str, action: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    data = {
        "doctype": doctype,
        "name": raw.get("name"),
        "docstatus": raw.get("docstatus"),
        "status": raw.get("disabled", 0) and "Disabled" or "Active",
        "summary": action,
        "next_actions": ["review_master_data"],
        "risk": {
            "level": "L3",
            "requires_confirmation_for_submit": False,
        },
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug={"raw_document": raw} if raw else result.debug,
    )


def _stock_traceability_result(result: ToolResult, *, doctype: str, action: str) -> ToolResult:
    if not result.ok:
        return result
    raw = result.data if isinstance(result.data, dict) else {}
    data = {
        "doctype": doctype,
        "name": raw.get("name"),
        "docstatus": raw.get("docstatus"),
        "status": raw.get("status") or (raw.get("disabled", 0) and "Disabled") or "Updated",
        "summary": action,
        "next_actions": ["audit_traceability_record"],
        "risk": {
            "level": "L4",
            "requires_confirmation_for_submit": False,
        },
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug={"raw_document": raw} if raw else result.debug,
    )


def _stock_preview_result(result: ToolResult, *, summary: str, next_actions: list[str]) -> ToolResult:
    if not result.ok:
        return result
    payload = result.data if isinstance(result.data, dict) else {"raw": result.data}
    data = {
        "doctype": None,
        "name": None,
        "docstatus": None,
        "status": payload.get("status", "preview"),
        "summary": summary,
        "next_actions": next_actions,
        "risk": {
            "level": "L1",
            "requires_confirmation_for_submit": False,
        },
        "preview": payload,
    }
    return ToolResult(
        ok=True,
        status_code=result.status_code,
        raw_status_code=result.raw_status_code,
        data=data,
        debug=result.debug,
    )


def _stock_document_impact_result(doctype: str, name: str, document: Any, ledger_entries: Any) -> ToolResult:
    doc = document if isinstance(document, dict) else {}
    ledger_rows = ledger_entries if isinstance(ledger_entries, list) else []
    total_qty = sum(float(row.get("actual_qty") or 0) for row in ledger_rows if isinstance(row, dict))
    total_value_difference = sum(float(row.get("stock_value_difference") or 0) for row in ledger_rows if isinstance(row, dict))
    owner_module = "Sales" if doctype == "Delivery Note" else "Buying"
    return ToolResult(
        ok=True,
        data={
            "doctype": doctype,
            "name": name,
            "docstatus": doc.get("docstatus"),
            "status": doc.get("status"),
            "summary": f"Read stock impact for {doctype} {name}: {len(ledger_rows)} stock ledger rows.",
            "next_actions": ["review_stock_ledger_entries", f"use_{owner_module.lower()}_module_for_draft_changes"],
            "risk": {
                "level": "L0",
                "requires_confirmation_for_submit": False,
            },
            "boundary": {
                "owner_module": owner_module,
                "stock_module_role": "read_stock_impact_only",
                "draft_creation_tool": "erpnext.buying.create_purchase_receipt_draft" if doctype == "Purchase Receipt" else None,
            },
            "impact": {
                "ledger_entry_count": len(ledger_rows),
                "total_actual_qty": total_qty,
                "total_stock_value_difference": total_value_difference,
                "ledger_entries": ledger_rows,
            },
            "document": {
                "customer": doc.get("customer"),
                "supplier": doc.get("supplier"),
                "posting_date": doc.get("posting_date"),
                "modified": doc.get("modified"),
            },
        },
        debug={"raw_document": doc},
    )


def _require_stock_confirmation(doctype: str | None, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in STOCK_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Stock confirmation required for {doctype}.",
            error_type="stock_confirmation_required",
            user_message="库存提交/取消会影响库存数量或成本，需要 confirmation 的 confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None


def _require_traceability_confirmation(doctype: str, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Traceability confirmation required for {doctype}.",
            error_type="traceability_confirmation_required",
            user_message="批次/序列号更新会影响库存追溯，需要 confirmation 的 confirmed_by、confirmed_at、confirmation_text 和 reason。",
            data={
                "doctype": doctype,
                "name": name,
                "status": "confirmation_required",
                "summary": f"{doctype} traceability update requires explicit confirmation.",
                "next_actions": ["collect_confirmation", "retry_update"],
                "risk": {"level": "L4", "requires_confirmation_for_submit": False},
            },
            meta={
                "risk_level": "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None


def _require_buying_confirmation(doctype: str | None, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in BUYING_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Buying confirmation required for {doctype}.",
            error_type="buying_confirmation_required",
            user_message="采购提交会形成业务承诺或库存影响，需要 confirmation 的 confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None


def _require_accounting_write_confirmation(
    action: str,
    doctype: str | None,
    name: str | None,
    confirmation: dict[str, Any] | None,
) -> ToolResult | None:
    if doctype not in ACCOUNTING_WRITE_GUARDED_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Accounting write confirmation required for {doctype}.",
            error_type="financial_confirmation_required",
            user_message="财务凭证或财务主数据写入属于高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            data={
                "doctype": doctype,
                "name": name,
                "status": "Confirmation Required",
                "summary": f"L5_FINANCIAL confirmation required before {action} can be executed.",
                "next_actions": ["obtain_explicit_finance_confirmation", "use_accounting_module_tool_when_available", "retry_with_confirmation_metadata"],
                "risk": {
                    "level": "L5_FINANCIAL",
                    "confirmation_required": True,
                    "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                },
            },
            meta={
                "risk_level": "L5_FINANCIAL",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "action": action,
                "doctype": doctype,
                "name": name,
            },
        )
    return None


def _call_method_doctype(method: str, args: dict[str, Any]) -> str | None:
    if method in {"agent_bridge.api.submit_document", "agent_bridge.api.cancel_document"}:
        return args.get("doctype")
    if method in {"frappe.client.insert", "frappe.client.save"}:
        doc = args.get("doc") or args.get("docs")
        if isinstance(doc, dict):
            return doc.get("doctype")
        return args.get("doctype")
    return args.get("doctype") or args.get("dt")


def _call_method_name(args: dict[str, Any]) -> str | None:
    doc = args.get("doc") or args.get("docs")
    if isinstance(doc, dict) and doc.get("name"):
        return doc.get("name")
    return args.get("name") or args.get("dn")


def _require_asset_confirmation(doctype: str | None, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in ASSET_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Asset confirmation required for {doctype}.",
            error_type="asset_confirmation_required",
            user_message="资产提交、资本化、价值调整、报废或出售属于高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L5_FINANCIAL" if doctype in ASSET_FINANCIAL_DOCTYPES else "L4",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
                "name": name,
            },
        )
    return None

def _require_l5_financial_confirmation(action: str, name: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"L5 financial confirmation required for {action}.",
            error_type="financial_confirmation_required",
            user_message="此财务操作属于 L5_FINANCIAL 高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            data={
                "doctype": None,
                "name": name,
                "status": "Confirmation Required",
                "summary": f"L5_FINANCIAL confirmation required before {action} can be executed.",
                "next_actions": ["obtain_explicit_finance_confirmation", "retry_with_confirmation_metadata"],
                "risk": {
                    "level": "L5_FINANCIAL",
                    "confirmation_required": True,
                    "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                },
            },
            meta={
                "risk_level": "L5_FINANCIAL",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "action": action,
                "name": name,
            },
        )
    return None

def _require_financial_confirmation(doctype: str | None, confirmation: dict[str, Any] | None) -> ToolResult | None:
    if doctype not in ACCOUNTING_SUBMITTABLE_DOCTYPES:
        return None
    confirmation = confirmation or {}
    missing = [
        field
        for field in ("confirmed_by", "confirmed_at", "confirmation_text", "reason")
        if not confirmation.get(field)
    ]
    if missing:
        return ToolResult(
            ok=False,
            error=f"Financial confirmation required for {doctype}.",
            error_type="financial_confirmation_required",
            user_message="财务提交/取消属于 L5_FINANCIAL 高风险操作，需要 confirmation.confirmed_by、confirmed_at、confirmation_text 和 reason。",
            meta={
                "risk_level": "L5_FINANCIAL",
                "required_confirmation_fields": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
                "doctype": doctype,
            },
        )
    return None
