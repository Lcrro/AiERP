from __future__ import annotations

from typing import Any

from ..schemas import ToolResult
from .common import *

class BuyingToolsMixin:
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
