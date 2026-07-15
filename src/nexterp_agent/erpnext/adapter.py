from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from .client import ERPNextClient
from .modules.accounting import AccountingToolsMixin
from .modules.assets import AssetsToolsMixin
from .modules.buying import BuyingToolsMixin
from .modules.common import *
from .modules.generic import GenericToolsMixin
from .modules.projects import ProjectsToolsMixin
from .modules.stock import StockToolsMixin
from .modules.users import UsersPermissionsToolsMixin
from .schemas import ToolCall, ToolResult


class ERPNextAdapter(
    GenericToolsMixin,
    UsersPermissionsToolsMixin,
    AssetsToolsMixin,
    BuyingToolsMixin,
    AccountingToolsMixin,
    StockToolsMixin,
    ProjectsToolsMixin,
):
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
            "erpnext.buying.get_pending_procurement_items": self._buying_get_pending_procurement_items,
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
            "erpnext.buying.create_purchase_order_from_supplier_quotation_draft": self._buying_create_purchase_order_from_supplier_quotation_draft,
            "erpnext.buying.create_purchase_order_from_material_request_draft": self._buying_create_purchase_order_from_material_request_draft,
            "erpnext.buying.create_purchase_receipt_draft": self._buying_create_purchase_receipt_draft,
            "erpnext.buying.create_purchase_receipt_from_purchase_order_draft": self._buying_create_purchase_receipt_from_purchase_order_draft,
            "erpnext.buying.record_purchase_receipt_discrepancy": self._buying_record_purchase_receipt_discrepancy,
            "erpnext.buying.get_purchase_receipt_return_context": self._buying_get_purchase_receipt_return_context,
            "erpnext.buying.create_purchase_receipt_return_draft": self._buying_create_purchase_receipt_return_draft,
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
            "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft": self._accounting_create_purchase_invoice_from_purchase_receipt_draft,
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
            "erpnext.stock.create_quality_inspection_draft": self._stock_create_quality_inspection_draft,
            "erpnext.stock.verify_purchase_receipt_stock_impact": self._stock_verify_purchase_receipt_stock_impact,
            "erpnext.stock.get_item_lifecycle_summary": self._stock_get_item_lifecycle_summary,
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
            "erpnext.projects.get_project_cost_context": self._projects_get_project_cost_context,
            "erpnext.projects.get_material_issue_context": self._projects_get_material_issue_context,
            "erpnext.projects.create_material_issue_draft": self._projects_create_material_issue_draft,
            "erpnext.projects.verify_material_issue_cost_impact": self._projects_verify_material_issue_cost_impact,
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
