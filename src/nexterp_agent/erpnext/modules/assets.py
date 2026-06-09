from __future__ import annotations

from typing import Any

from ..schemas import ToolResult
from .common import *

class AssetsToolsMixin:
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
