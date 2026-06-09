from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"toolcall_{uuid4().hex}")
    created_at: str = field(default_factory=_now_iso)
    reason: str | None = None
    risk_level: str = "L0"
    user_context: dict[str, Any] = field(default_factory=dict)
    validation_error: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolCall":
        return cls(
            tool=payload["tool"],
            arguments=payload.get("arguments") or {},
            id=payload.get("id") or f"toolcall_{uuid4().hex}",
            created_at=payload.get("created_at") or _now_iso(),
            reason=payload.get("reason"),
            risk_level=payload.get("risk_level") or infer_risk_level_for_call(payload),
            user_context=payload.get("user_context") or {},
            validation_error=payload.get("validation_error"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "created_at": self.created_at,
            "tool": self.tool,
            "arguments": self.arguments,
            "risk_level": self.risk_level,
            "user_context": self.user_context,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.validation_error:
            payload["validation_error"] = self.validation_error
        return payload


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    status_code: int | None = None
    raw_status_code: int | None = None
    error: str | None = None
    error_type: str | None = None
    user_message: str | None = None
    tool_call_id: str | None = None
    duration_ms: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)

    def with_call(self, call: ToolCall, duration_ms: int | None = None) -> "ToolResult":
        return replace(
            self,
            tool_call_id=call.id,
            duration_ms=duration_ms if duration_ms is not None else self.duration_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "data": self.data,
        }
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.duration_ms is not None:
            payload["duration_ms"] = self.duration_ms
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.raw_status_code is not None:
            payload["raw_status_code"] = self.raw_status_code
        if self.error:
            payload["error"] = self.error
        if self.error_type:
            payload["error_type"] = self.error_type
        if self.user_message:
            payload["user_message"] = self.user_message
        if self.meta:
            payload["meta"] = self.meta
        if self.debug:
            payload["debug"] = self.debug
        return payload


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
        "erpnext.assets.search_assets",
        "erpnext.assets.search_asset_categories",
        "erpnext.assets.search_asset_locations",
        "erpnext.assets.get_financial_snapshot",
        "erpnext.assets.get_depreciation_schedule",
    }:
        return "L0"
    if tool in {
        "erpnext.stock.resolve_item",
        "erpnext.stock.preview_valuation",
        "erpnext.stock.allocate_shortages",
        "erpnext.assets.prepare_disposal_or_sale",
        "erpnext.buying.get_supplier_procurement_profile",
        "erpnext.accounting.prepare_payment_allocation",
        "erpnext.accounting.prepare_invoice_taxes",
        "erpnext.accounting.prepare_bank_reconciliation",
        "erpnext.buying.compare_supplier_quotations",
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
    if tool in {"erpnext.create_todo", "erpnext.add_comment", "erpnext.assign_to", "erpnext.attach_file"}:
        return "L2"
    if tool in {
        "erpnext.buying.create_supplier_draft",
        "erpnext.buying.create_supplier_group_draft",
        "erpnext.buying.create_material_request_draft",
        "erpnext.buying.create_request_for_quotation_draft",
        "erpnext.buying.create_supplier_quotation_draft",
        "erpnext.buying.create_purchase_order_draft",
        "erpnext.buying.create_purchase_receipt_draft",
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
        "erpnext.assets.create_asset_draft",
        "erpnext.assets.create_movement_draft",
        "erpnext.assets.create_maintenance_draft",
        "erpnext.assets.create_maintenance_log_draft",
        "erpnext.assets.create_repair_draft",
        "erpnext.assets.create_value_adjustment_draft",
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
