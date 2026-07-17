from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS


class ToolExposure(str, Enum):
    AGENT_VISIBLE = "agent_visible"
    RUNTIME_INTERNAL = "runtime_internal"
    DEVELOPER_ONLY = "developer_only"


REGISTERED_TOOL_NAMES = frozenset(schema["name"] for schema in ERPNext_TOOL_SCHEMAS)

DEVELOPER_ONLY_TOOLS = frozenset(
    {
        "erpnext.create_document",
        "erpnext.update_document",
        "erpnext.delete_document",
        "erpnext.call_method",
        "erpnext.setup_item_master",
        "erpnext.create_item_from_intent",
    }
)

RUNTIME_INTERNAL_TOOLS = frozenset(
    {
        "erpnext.search_documents",
        "erpnext.count_documents",
        "erpnext.get_document",
        "erpnext.document_exists",
        "erpnext.resolve_link",
        "erpnext.validate_fields",
        "erpnext.get_doctype_schema",
        "erpnext.submit_document",
        "erpnext.cancel_document",
        "erpnext.amend_document",
        "erpnext.run_report",
        "erpnext.prepare_item_from_intent",
    }
)

COMMON_AGENT_TOOLS = frozenset(
    {
        "erpnext.get_logged_user",
        "erpnext.search_items",
        "erpnext.create_todo",
        "erpnext.add_comment",
        "erpnext.get_comments",
        "erpnext.assign_to",
        "erpnext.clear_assignment",
        "erpnext.attach_file",
        "erpnext.list_attachments",
        "erpnext.get_workflow_actions",
        "erpnext.apply_workflow",
    }
)

STOCK_READ_TOOLS = frozenset(
    {
        "erpnext.stock.get_balance",
        "erpnext.stock.get_item_locations",
        "erpnext.stock.get_ledger_entries",
        "erpnext.stock.list_batch_balances",
        "erpnext.stock.search_batches",
        "erpnext.stock.search_serial_numbers",
        "erpnext.stock.list_pick_lists",
        "erpnext.stock.list_reservations",
        "erpnext.stock.preview_valuation",
        "erpnext.stock.list_delivery_notes",
        "erpnext.stock.list_purchase_receipts",
        "erpnext.stock.get_document_impact",
        "erpnext.stock.list_item_reorders",
        "erpnext.stock.list_quality_inspections",
        "erpnext.stock.get_item_lifecycle_summary",
        "erpnext.stock.list_warehouses",
        "erpnext.stock.list_item_groups",
        "erpnext.stock.list_uoms",
        "erpnext.stock.get_transfer_context",
        "erpnext.stock.verify_transfer_impact",
    }
)

STOCK_MOVEMENT_TOOLS = frozenset(
    {
        "erpnext.stock.get_transfer_context",
        "erpnext.stock.create_transfer_draft",
        "erpnext.stock.verify_transfer_impact",
        "erpnext.stock.submit_document",
    }
)

PROJECT_READ_TOOLS = frozenset(
    {
        "erpnext.projects.get_project_cost_context",
        "erpnext.projects.get_material_issue_context",
        "erpnext.projects.verify_material_issue_cost_impact",
    }
)

PROFILE_ALIASES = {
    "manager_agent": "manager",
    "material_equipment_agent": "procurement",
    "operations_agent": "operations",
    "project_agent": "project",
    "technical_agent": "technical",
    "material_clerk_agent": "project",
    "admin_agent": "system_admin",
    "finance_agent": "finance",
}


def infer_tool_exposure(tool_name: str) -> ToolExposure:
    if tool_name in DEVELOPER_ONLY_TOOLS:
        return ToolExposure.DEVELOPER_ONLY
    if tool_name in RUNTIME_INTERNAL_TOOLS:
        return ToolExposure.RUNTIME_INTERNAL
    return ToolExposure.AGENT_VISIBLE


def filter_tool_schemas_for_policy(policy: "ToolAccessPolicy", *, origin: str = "agent") -> list[dict]:
    return [schema for schema in ERPNext_TOOL_SCHEMAS if policy.decide(schema["name"], origin=origin).allowed]


@dataclass(frozen=True)
class ToolAccessDecision:
    allowed: bool
    reason: str
    exposure: ToolExposure


@dataclass(frozen=True)
class ToolAccessPolicy:
    """Role/workbench-level ToolCall allowlist.

    ERPNext remains the final permission authority. This policy only controls
    which ToolCalls a model-originated request may ask the adapter to execute.
    """

    profile_name: str
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    allowed_prefixes: tuple[str, ...] = ()
    blocked_tools: frozenset[str] = field(default_factory=frozenset)
    allow_runtime_internal: bool = False
    allow_developer_tools: bool = False

    def decide(self, tool_name: str, *, origin: str = "agent") -> ToolAccessDecision:
        exposure = infer_tool_exposure(tool_name)
        if tool_name not in REGISTERED_TOOL_NAMES:
            return ToolAccessDecision(False, "unregistered_tool", exposure)

        if tool_name in self.blocked_tools:
            return ToolAccessDecision(False, "blocked_by_profile", exposure)

        if exposure is ToolExposure.DEVELOPER_ONLY and not self.allow_developer_tools:
            return ToolAccessDecision(False, "developer_only_tool", exposure)

        if exposure is ToolExposure.RUNTIME_INTERNAL and origin != "runtime":
            return ToolAccessDecision(False, "runtime_internal_tool", exposure)

        if exposure is ToolExposure.RUNTIME_INTERNAL and not self.allow_runtime_internal:
            return ToolAccessDecision(False, "runtime_internal_not_enabled", exposure)

        if tool_name in self.allowed_tools:
            return ToolAccessDecision(True, "explicit_tool", exposure)

        if any(tool_name.startswith(prefix) for prefix in self.allowed_prefixes):
            return ToolAccessDecision(True, "profile_prefix", exposure)

        if exposure is ToolExposure.DEVELOPER_ONLY and self.allow_developer_tools:
            return ToolAccessDecision(True, "developer_profile", exposure)

        return ToolAccessDecision(False, "not_in_profile_allowlist", exposure)

    def allowed_schema_names(self, *, origin: str = "agent") -> list[str]:
        return sorted(name for name in REGISTERED_TOOL_NAMES if self.decide(name, origin=origin).allowed)


def _tools_with_prefix(prefix: str) -> frozenset[str]:
    return frozenset(name for name in REGISTERED_TOOL_NAMES if name.startswith(prefix))


def make_tool_access_policy(
    profile_name: str,
    *,
    extra_allowed_tools: Iterable[str] = (),
    blocked_tools: Iterable[str] = (),
    allow_runtime_internal: bool = False,
    allow_developer_tools: bool = False,
) -> ToolAccessPolicy:
    profile_key = profile_name.lower().strip()
    profile_key = PROFILE_ALIASES.get(profile_key, profile_key)
    extra = frozenset(extra_allowed_tools)
    blocked = frozenset(blocked_tools)

    if profile_key in {"developer", "dev"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=REGISTERED_TOOL_NAMES,
            blocked_tools=blocked,
            allow_runtime_internal=True,
            allow_developer_tools=True,
        )

    if profile_key in {"system_admin", "admin", "administrator", "系统管理员"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS | _tools_with_prefix("erpnext.users.") | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"procurement", "buying", "buyer", "采购", "采购员", "采购主管"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS
            | _tools_with_prefix("erpnext.buying.")
            | STOCK_READ_TOOLS
            | STOCK_MOVEMENT_TOOLS
            | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"stock", "warehouse", "仓库", "仓库员", "仓库主管"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS | _tools_with_prefix("erpnext.stock.") | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"accounting", "finance", "财务", "财务主管"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS | _tools_with_prefix("erpnext.accounting.") | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"asset", "assets", "资产", "资产管理员"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS | _tools_with_prefix("erpnext.assets.") | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"project", "projects", "项目", "项目经理", "班组长"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS
            | _tools_with_prefix("erpnext.projects.")
            | STOCK_READ_TOOLS
            | frozenset(
                {
                    "erpnext.buying.create_material_request_draft",
                    "erpnext.buying.submit_document",
                    "erpnext.stock.submit_document",
                }
            )
            | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"technical", "技术", "技术负责人"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS | STOCK_READ_TOOLS | PROJECT_READ_TOOLS | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"operations", "经营", "经营主管"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS
            | STOCK_READ_TOOLS
            | PROJECT_READ_TOOLS
            | frozenset(
                {
                    "erpnext.buying.get_pending_procurement_items",
                    "erpnext.buying.search_suppliers",
                    "erpnext.buying.search_supplier_scorecards",
                    "erpnext.buying.get_supplier_procurement_profile",
                    "erpnext.buying.compare_supplier_quotations",
                    "erpnext.buying.search_item_suppliers",
                    "erpnext.buying.search_item_prices",
                    "erpnext.buying.run_purchase_analysis",
                    "erpnext.accounting.general_ledger",
                    "erpnext.accounting.accounts_receivable",
                    "erpnext.accounting.accounts_payable",
                    "erpnext.accounting.financial_report",
                }
            )
            | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    if profile_key in {"manager", "management", "老板", "总经理", "管理层"}:
        return ToolAccessPolicy(
            profile_name=profile_name,
            allowed_tools=COMMON_AGENT_TOOLS
            | STOCK_READ_TOOLS
            | frozenset(
                {
                    "erpnext.buying.search_suppliers",
                    "erpnext.buying.search_supplier_scorecards",
                    "erpnext.buying.get_supplier_procurement_profile",
                    "erpnext.buying.compare_supplier_quotations",
                    "erpnext.buying.generate_purchase_suggestions",
                    "erpnext.buying.search_item_suppliers",
                    "erpnext.buying.search_item_prices",
                    "erpnext.buying.get_buying_settings",
                    "erpnext.buying.run_purchase_analysis",
                    "erpnext.accounting.general_ledger",
                    "erpnext.accounting.accounts_receivable",
                    "erpnext.accounting.accounts_payable",
                    "erpnext.accounting.financial_report",
                    "erpnext.projects.get_project_cost_context",
                    "erpnext.projects.verify_material_issue_cost_impact",
                }
            )
            | extra,
            blocked_tools=blocked,
            allow_runtime_internal=allow_runtime_internal,
            allow_developer_tools=allow_developer_tools,
        )

    return ToolAccessPolicy(
        profile_name=profile_name,
        allowed_tools=COMMON_AGENT_TOOLS | extra,
        blocked_tools=blocked,
        allow_runtime_internal=allow_runtime_internal,
        allow_developer_tools=allow_developer_tools,
    )
