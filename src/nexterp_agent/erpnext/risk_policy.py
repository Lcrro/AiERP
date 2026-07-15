from __future__ import annotations

from typing import Any


def infer_risk_level(tool: str) -> str:
    if tool in {
        "erpnext.users.create_user_draft",
        "erpnext.users.set_user_enabled",
        "erpnext.users.assign_roles",
        "erpnext.users.create_user_permission",
        "erpnext.users.delete_user_permission",
        "erpnext.users.preview_permission_policy_change",
    }:
        return "L5_ADMIN"
    if tool in {
        "erpnext.accounting.submit_financial_document",
        "erpnext.accounting.apply_bank_reconciliation",
    }:
        return "L5_FINANCIAL"
    if tool in {
        "erpnext.users.list_users",
        "erpnext.users.get_user_access_summary",
        "erpnext.users.list_roles",
        "erpnext.users.list_role_profiles",
        "erpnext.users.preview_role_profile_roles",
        "erpnext.users.list_user_permissions",
        "erpnext.users.list_shared_documents",
        "erpnext.users.list_access_logs",
        "erpnext.users.list_activity_logs",
        "erpnext.users.get_permission_metadata",
        "erpnext.users.preview_effective_permissions",
        "erpnext.users.check_server_permission",
    }:
        return "L0"
    if tool in {
        "erpnext.buying.get_pending_procurement_items",
        "erpnext.buying.search_suppliers",
        "erpnext.buying.search_supplier_scorecards",
        "erpnext.buying.search_item_suppliers",
        "erpnext.buying.search_item_prices",
        "erpnext.buying.get_buying_settings",
        "erpnext.buying.generate_purchase_suggestions",
        "erpnext.buying.run_purchase_analysis",
        "erpnext.stock.get_balance",
        "erpnext.stock.get_item_locations",
        "erpnext.stock.get_ledger_entries",
        "erpnext.stock.get_stock_settings",
        "erpnext.stock.search_batches",
        "erpnext.stock.list_batch_balances",
        "erpnext.stock.search_serial_numbers",
        "erpnext.stock.list_warehouses",
        "erpnext.stock.list_item_groups",
        "erpnext.stock.list_uoms",
        "erpnext.stock.list_pick_lists",
        "erpnext.stock.list_reservations",
        "erpnext.stock.list_delivery_notes",
        "erpnext.stock.list_purchase_receipts",
        "erpnext.stock.get_document_impact",
        "erpnext.stock.list_item_reorders",
        "erpnext.stock.list_quality_inspections",
        "erpnext.stock.verify_purchase_receipt_stock_impact",
        "erpnext.stock.get_item_lifecycle_summary",
        "erpnext.assets.search_assets",
        "erpnext.assets.search_asset_categories",
        "erpnext.assets.search_asset_locations",
        "erpnext.assets.get_financial_snapshot",
        "erpnext.assets.get_depreciation_schedule",
        "erpnext.projects.get_project_cost_context",
        "erpnext.projects.verify_material_issue_cost_impact",
    }:
        return "L0"
    if tool in {
        "erpnext.stock.resolve_item",
        "erpnext.stock.preview_valuation",
        "erpnext.stock.allocate_shortages",
        "erpnext.assets.prepare_disposal_or_sale",
        "erpnext.buying.get_supplier_procurement_profile",
        "erpnext.buying.get_purchase_receipt_return_context",
        "erpnext.accounting.prepare_payment_allocation",
        "erpnext.accounting.prepare_invoice_taxes",
        "erpnext.accounting.prepare_bank_reconciliation",
        "erpnext.buying.compare_supplier_quotations",
        "erpnext.projects.get_material_issue_context",
    }:
        return "L1"
    if tool in {
        "erpnext.get_logged_user",
        "erpnext.search_documents",
        "erpnext.search_items",
        "erpnext.count_documents",
        "erpnext.get_document",
        "erpnext.get_doctype_schema",
        "erpnext.document_exists",
        "erpnext.resolve_link",
        "erpnext.validate_fields",
        "erpnext.get_workflow_actions",
        "erpnext.run_report",
        "erpnext.get_comments",
        "erpnext.list_attachments",
        "erpnext.prepare_item_from_intent",
        "erpnext.accounting.get_report_filters",
        "erpnext.accounting.search_accounts",
        "erpnext.accounting.search_cost_centers",
        "erpnext.accounting.search_budgets",
        "erpnext.accounting.search_fiscal_years",
        "erpnext.accounting.search_accounting_periods",
        "erpnext.accounting.search_payment_terms",
        "erpnext.accounting.search_tax_templates",
        "erpnext.accounting.general_ledger",
        "erpnext.accounting.accounts_receivable",
        "erpnext.accounting.accounts_payable",
        "erpnext.accounting.financial_report",
    }:
        return "L0"
    if tool in {"erpnext.create_todo", "erpnext.add_comment", "erpnext.assign_to", "erpnext.attach_file", "erpnext.buying.record_purchase_receipt_discrepancy"}:
        return "L2"
    if tool in {
        "erpnext.buying.create_supplier_draft",
        "erpnext.buying.create_supplier_group_draft",
        "erpnext.buying.create_material_request_draft",
        "erpnext.buying.create_request_for_quotation_draft",
        "erpnext.buying.create_supplier_quotation_draft",
        "erpnext.buying.create_purchase_order_draft",
        "erpnext.buying.create_purchase_order_from_material_request_draft",
        "erpnext.buying.create_purchase_receipt_draft",
        "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
        "erpnext.buying.create_purchase_receipt_return_draft",
    }:
        return "L3"
    if tool in {
        "erpnext.create_document",
        "erpnext.update_document",
        "erpnext.clear_assignment",
        "erpnext.create_item_from_intent",
        "erpnext.setup_item_master",
        "erpnext.accounting.create_journal_entry_draft",
        "erpnext.accounting.create_payment_entry_draft",
        "erpnext.accounting.create_sales_invoice_draft",
        "erpnext.accounting.create_purchase_invoice_draft",
        "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
        "erpnext.accounting.create_period_closing_voucher_draft",
        "erpnext.accounting.create_budget_draft",
        "erpnext.accounting.update_budget_draft",
        "erpnext.stock.create_entry_draft",
        "erpnext.stock.create_reconciliation_draft",
        "erpnext.stock.create_warehouse",
        "erpnext.stock.update_warehouse",
        "erpnext.stock.create_item_group",
        "erpnext.stock.update_item_group",
        "erpnext.stock.create_uom",
        "erpnext.stock.update_uom",
        "erpnext.stock.create_batch",
        "erpnext.stock.create_serial_no",
        "erpnext.stock.create_pick_list_draft",
        "erpnext.stock.create_reservation_draft",
        "erpnext.stock.create_quality_inspection_draft",
        "erpnext.assets.create_asset_draft",
        "erpnext.assets.create_movement_draft",
        "erpnext.assets.create_maintenance_draft",
        "erpnext.assets.create_maintenance_log_draft",
        "erpnext.assets.create_repair_draft",
        "erpnext.assets.create_value_adjustment_draft",
        "erpnext.projects.create_material_issue_draft",
    }:
        return "L3"
    if tool in {
        "erpnext.delete_document",
        "erpnext.submit_document",
        "erpnext.cancel_document",
        "erpnext.amend_document",
        "erpnext.apply_workflow",
        "erpnext.delete_attachment",
        "erpnext.buying.submit_document",
        "erpnext.stock.submit_document",
        "erpnext.stock.update_batch",
        "erpnext.stock.update_serial_no",
        "erpnext.assets.submit_document",
    }:
        return "L4"
    return "L1"


def infer_risk_level_for_call(payload: dict[str, Any]) -> str:
    tool = payload["tool"]
    arguments = payload.get("arguments") or {}
    financial_doctypes = {
        "Journal Entry",
        "Payment Entry",
        "Sales Invoice",
        "Purchase Invoice",
        "Period Closing Voucher",
    }
    if tool in {"erpnext.submit_document", "erpnext.cancel_document"} and arguments.get("doctype") in financial_doctypes:
        return "L5_FINANCIAL"
    if tool == "erpnext.call_method" and arguments.get("method") in {
        "agent_bridge.api.submit_document",
        "agent_bridge.api.cancel_document",
    }:
        method_args = arguments.get("args") or {}
        if isinstance(method_args, dict) and method_args.get("doctype") in financial_doctypes:
            return "L5_FINANCIAL"
    return infer_risk_level(tool)
