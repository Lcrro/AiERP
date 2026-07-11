from __future__ import annotations

from datetime import date
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
        if args.get("schedule_date"):
            for item in items:
                item.setdefault("schedule_date", args["schedule_date"])
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
        price_lists: set[str] = set()
        for item in items:
            price_list = self._fill_supplier_item_price(item, args["supplier"])
            if price_list:
                price_lists.add(price_list)
        data = _without_empty(
            {
                "doctype": "Purchase Order",
                "supplier": args["supplier"],
                "transaction_date": args.get("transaction_date"),
                "schedule_date": args.get("schedule_date"),
                "company": args.get("company"),
                "currency": args.get("currency"),
                "buying_price_list": next(iter(price_lists)) if len(price_lists) == 1 else None,
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

    def _fill_supplier_item_price(self, item: dict[str, Any], supplier: str) -> str | None:
        if (_float_or_none(item.get("rate")) or 0) > 0:
            return None
        filters: dict[str, Any] = {
            "item_code": item["item_code"],
            "supplier": supplier,
            "buying": 1,
        }
        if item.get("uom"):
            filters["uom"] = item["uom"]
        result = self.client.search_documents(
            "Item Price",
            filters=filters,
            fields=["name", "price_list", "price_list_rate", "currency", "uom", "valid_from", "valid_upto"],
            limit=20,
            order_by="valid_from desc",
        )
        if not result.ok or not isinstance(result.data, list):
            return None
        today = date.today().isoformat()
        for candidate in result.data:
            valid_from = str(candidate.get("valid_from") or "")
            valid_upto = str(candidate.get("valid_upto") or "")
            rate = _float_or_none(candidate.get("price_list_rate"))
            if not rate or (valid_from and valid_from > today) or (valid_upto and valid_upto < today):
                continue
            item["rate"] = rate
            item["price_list_rate"] = rate
            return str(candidate.get("price_list") or "") or None
        return None

    def _buying_create_purchase_order_from_material_request_draft(self, args: dict[str, Any]) -> ToolResult:
        material_request = args["material_request"]
        result = self.client.get_document("Material Request", material_request)
        if not result.ok:
            return result
        doc = result.data if isinstance(result.data, dict) else {}
        guard = _validate_material_request_for_purchase_order(doc, material_request)
        if guard:
            return guard

        context = _material_request_purchase_order_context(doc, args)
        errors = context["errors"]
        items = context["items"]
        if errors or not items:
            return ToolResult(
                ok=False,
                error="Purchase Order draft cannot be created from the current Material Request context.",
                error_type="validation_error",
                user_message="无法从该材料申请创建采购订单草稿：请检查材料申请状态、物料行和未订购数量。",
                data={
                    "doctype": "Material Request",
                    "name": material_request,
                    "status": "Purchase Order Draft Blocked",
                    "summary": "Review Material Request context before creating a Purchase Order draft.",
                    "errors": errors,
                    "warnings": context["warnings"],
                    "next_actions": ["review_material_request", "retry_with_valid_rows"],
                    "risk": {"level": "L1", "requires_confirmation_for_submit": False},
                },
                debug={"raw_material_request": doc},
            )

        draft_result = self._buying_create_purchase_order_draft(
            {
                "supplier": args["supplier"],
                "transaction_date": args.get("transaction_date"),
                "schedule_date": args.get("schedule_date") or context["default_schedule_date"],
                "company": args.get("company") or doc.get("company"),
                "currency": args.get("currency"),
                "items": items,
            }
        )
        if draft_result.ok and isinstance(draft_result.data, dict):
            draft_result.data["source_material_request"] = material_request
            draft_result.data["source_item_count"] = len(items)
            draft_result.data["warnings"] = context["warnings"]
            draft_result.data["summary"] = (
                f"Created Purchase Order draft from Material Request {material_request} "
                f"for {args['supplier']} with {len(items)} item row(s)."
            )
        if draft_result.ok and isinstance(draft_result.debug, dict):
            draft_result.debug["material_request_context"] = context
        return draft_result

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

    def _buying_create_purchase_receipt_from_purchase_order_draft(self, args: dict[str, Any]) -> ToolResult:
        purchase_order = args["purchase_order"]
        result = self.client.get_document("Purchase Order", purchase_order)
        if not result.ok:
            return result
        doc = result.data if isinstance(result.data, dict) else {}
        guard = _validate_purchase_order_for_purchase_receipt(doc, purchase_order)
        if guard:
            return guard

        context = _purchase_order_receipt_context(doc, args)
        errors = context["errors"]
        items = context["items"]
        if errors or not items:
            return ToolResult(
                ok=False,
                error="Purchase Receipt draft cannot be created from the current Purchase Order context.",
                error_type="validation_error",
                user_message="无法从该采购订单创建采购收货草稿：请检查采购订单状态、物料行和未收货数量。",
                data={
                    "doctype": "Purchase Order",
                    "name": purchase_order,
                    "status": "Purchase Receipt Draft Blocked",
                    "summary": "Review Purchase Order context before creating a Purchase Receipt draft.",
                    "errors": errors,
                    "warnings": context["warnings"],
                    "next_actions": ["review_purchase_order", "retry_with_valid_rows"],
                    "risk": {"level": "L1", "requires_confirmation_for_submit": False},
                },
                debug={"raw_purchase_order": doc},
            )

        draft_result = self._buying_create_purchase_receipt_draft(
            {
                "supplier": doc.get("supplier"),
                "posting_date": args.get("posting_date"),
                "company": args.get("company") or doc.get("company"),
                "items": items,
            }
        )
        if draft_result.ok and isinstance(draft_result.data, dict):
            draft_result.data["source_purchase_order"] = purchase_order
            draft_result.data["source_item_count"] = len(items)
            draft_result.data["warnings"] = context["warnings"]
            draft_result.data["summary"] = (
                f"Created Purchase Receipt draft from Purchase Order {purchase_order} "
                f"with {len(items)} item row(s)."
            )
        if draft_result.ok and isinstance(draft_result.debug, dict):
            draft_result.debug["purchase_order_context"] = context
        return draft_result

    def _buying_record_purchase_receipt_discrepancy(self, args: dict[str, Any]) -> ToolResult:
        purchase_receipt = args["purchase_receipt"]
        result = self.client.get_document("Purchase Receipt", purchase_receipt)
        if not result.ok:
            return result
        doc = result.data if isinstance(result.data, dict) else {}
        items = [row for row in args.get("items") or [] if isinstance(row, dict)]
        discrepancy = _purchase_receipt_discrepancy_summary(args, items)
        comment_content = _purchase_receipt_discrepancy_comment(purchase_receipt, discrepancy, items)

        comment = self.client.add_comment(
            "Purchase Receipt",
            purchase_receipt,
            comment_content,
            comment_email=args.get("comment_email") or "agent@example.com",
            comment_by=args.get("comment_by") or "Nexterp Agent",
        )
        if not comment.ok:
            return comment

        todo_result: ToolResult | None = None
        if args.get("create_todo", True):
            todo_result = self.client.create_todo(
                _purchase_receipt_discrepancy_todo_description(purchase_receipt, discrepancy),
                allocated_to=args.get("assigned_to"),
                priority=args.get("priority") or _priority_from_severity(discrepancy["severity"]),
                reference_type="Purchase Receipt",
                reference_name=purchase_receipt,
                date=args.get("due_date"),
            )
            if not todo_result.ok:
                return ToolResult(
                    ok=False,
                    error="Purchase Receipt discrepancy was commented, but follow-up ToDo creation failed.",
                    error_type=todo_result.error_type or "todo_creation_failed",
                    user_message="到货差异已写入评论，但跟进 ToDo 创建失败。",
                    data={
                        "doctype": "Purchase Receipt",
                        "name": purchase_receipt,
                        "status": "Partially Recorded",
                        "summary": "Comment was created, but ToDo creation failed.",
                        "discrepancy": discrepancy,
                        "comment": comment.data,
                        "todo_error": todo_result.to_dict(),
                        "next_actions": ["review_comment", "retry_create_todo"],
                        "risk": {"level": "L2", "writes_comment": True, "creates_todo": False, "does_not_submit": True},
                    },
                    debug={"raw_purchase_receipt": doc},
                )

        return_preview = None
        return_context = None
        if args.get("prepare_return", True) and doc.get("docstatus") == 1:
            return_requests = _purchase_receipt_discrepancy_return_requests(items)
            if return_requests or args.get("full_return"):
                return_context = _purchase_receipt_return_context(
                    doc,
                    {
                        "items": return_requests,
                        "full_return": bool(args.get("full_return")),
                        "reason": discrepancy["description"],
                    },
                )
                return_preview = {
                    "status": "Return Context Ready"
                    if return_context["return_items"] and not return_context["errors"]
                    else "Return Review Required",
                    "return_items": return_context["return_items"],
                    "warnings": return_context["warnings"],
                    "errors": return_context["errors"],
                }

        next_actions = ["review_discrepancy_record", "follow_up_supplier"]
        if return_preview and return_preview["status"] == "Return Context Ready":
            next_actions.append("create_purchase_receipt_return_draft")
        elif doc.get("docstatus") != 1:
            next_actions.append("submit_purchase_receipt_before_return")

        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data={
                "doctype": "Purchase Receipt",
                "name": purchase_receipt,
                "docstatus": doc.get("docstatus"),
                "status": "Discrepancy Recorded",
                "summary": f"Recorded receiving discrepancy on Purchase Receipt {purchase_receipt}.",
                "discrepancy": discrepancy,
                "comment": comment.data,
                "todo": todo_result.data if todo_result else None,
                "return_preview": return_preview,
                "next_actions": next_actions,
                "risk": {"level": "L2", "writes_comment": True, "creates_todo": bool(todo_result), "does_not_submit": True},
            },
            debug={"raw_purchase_receipt": doc, "return_context": return_context},
        )

    def _buying_get_purchase_receipt_return_context(self, args: dict[str, Any]) -> ToolResult:
        purchase_receipt = args["purchase_receipt"]
        result = self.client.get_document("Purchase Receipt", purchase_receipt)
        if not result.ok:
            return result
        doc = result.data if isinstance(result.data, dict) else {}
        validation_error = _validate_purchase_receipt_can_return(doc, purchase_receipt)
        if validation_error:
            return validation_error

        context = _purchase_receipt_return_context(doc, args)
        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data={
                "doctype": "Purchase Receipt",
                "name": purchase_receipt,
                "docstatus": doc.get("docstatus"),
                "status": "Return Context Ready" if context["return_items"] and not context["errors"] else "Return Review Required",
                "summary": (
                    f"Prepared return context for Purchase Receipt {purchase_receipt}: "
                    f"{len(context['return_items'])} returnable row(s), {len(context['errors'])} issue(s)."
                ),
                "original": _clean_mapping(
                    {
                        "supplier": doc.get("supplier"),
                        "supplier_name": doc.get("supplier_name"),
                        "company": doc.get("company"),
                        "currency": doc.get("currency"),
                        "posting_date": doc.get("posting_date"),
                        "project": doc.get("project"),
                        "cost_center": doc.get("cost_center"),
                    }
                ),
                "requested_items": args.get("items") or [],
                "return_items": context["return_items"],
                "warnings": context["warnings"],
                "errors": context["errors"],
                "next_actions": ["create_purchase_receipt_return_draft"] if context["return_items"] and not context["errors"] else ["review_return_request"],
                "risk": {"level": "L1", "writes_document": False},
            },
            debug={"raw_purchase_receipt": doc},
        )

    def _buying_create_purchase_receipt_return_draft(self, args: dict[str, Any]) -> ToolResult:
        context_result = self._buying_get_purchase_receipt_return_context(args)
        if not context_result.ok:
            return context_result
        context = context_result.data if isinstance(context_result.data, dict) else {}
        return_items = context.get("return_items") or []
        errors = context.get("errors") or []
        if errors or not return_items:
            return ToolResult(
                ok=False,
                error="Purchase Receipt return draft cannot be created from the current context.",
                error_type="validation_error",
                user_message="采购退货草稿无法创建：退货行不存在，或退货数量/明细有问题。",
                data={
                    "doctype": "Purchase Receipt",
                    "name": args["purchase_receipt"],
                    "status": "Return Draft Blocked",
                    "summary": "Review return context before creating a Purchase Receipt return draft.",
                    "errors": errors,
                    "warnings": context.get("warnings") or [],
                    "next_actions": ["review_return_context", "retry_with_valid_return_rows"],
                    "risk": {"level": "L1", "requires_confirmation_for_submit": False},
                },
                debug=context_result.debug,
            )

        doc = context_result.debug.get("raw_purchase_receipt") if isinstance(context_result.debug, dict) else {}
        doc = doc if isinstance(doc, dict) else {}
        reason = args.get("reason")
        items = [_purchase_receipt_return_draft_item(row, reason) for row in return_items]
        data = _without_empty(
            {
                "doctype": "Purchase Receipt",
                "naming_series": "MAT-PR-RET-.YYYY.-",
                "supplier": doc.get("supplier"),
                "company": doc.get("company"),
                "posting_date": args.get("posting_date"),
                "currency": doc.get("currency"),
                "is_return": 1,
                "return_against": args["purchase_receipt"],
                "project": doc.get("project"),
                "cost_center": doc.get("cost_center"),
                "remarks": reason or f"Return against Purchase Receipt {args['purchase_receipt']}",
                "items": items,
                "docstatus": 0,
            }
        )
        result = self.client.create_document("Purchase Receipt", data)
        wrapped = _module_draft_result(
            result,
            doctype="Purchase Receipt",
            summary=f"Created Purchase Receipt return draft against {args['purchase_receipt']} with {len(items)} item row(s).",
            risk_level="L3",
            submit_tool="erpnext.buying.submit_document",
        )
        if wrapped.ok and isinstance(wrapped.data, dict):
            wrapped.data["return_against"] = args["purchase_receipt"]
            wrapped.data["return_item_count"] = len(items)
        if wrapped.ok and isinstance(wrapped.debug, dict):
            wrapped.debug["purchase_receipt_return_context"] = context
        return wrapped

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
            "project",
            "cost_center",
            "material_request",
            "material_request_item",
            "request_for_quotation",
            "supplier_quotation",
            "purchase_order",
            "purchase_order_item",
        }
        return _without_empty({field: row.get(field) for field in allowed_fields})


def _validate_material_request_for_purchase_order(doc: dict[str, Any], material_request: str) -> ToolResult | None:
    if doc.get("docstatus") != 1:
        return ToolResult(
            ok=False,
            error=f"Material Request {material_request} is not submitted.",
            error_type="validation_error",
            user_message="只有已提交的采购类材料申请才能生成采购订单草稿。",
            data={
                "doctype": "Material Request",
                "name": material_request,
                "docstatus": doc.get("docstatus"),
                "status": "Not Submitted",
                "summary": "Submit the Material Request before creating a Purchase Order from it.",
                "next_actions": ["submit_material_request", "retry_purchase_order_creation"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    material_request_type = doc.get("material_request_type")
    if material_request_type and material_request_type != "Purchase":
        return ToolResult(
            ok=False,
            error=f"Material Request {material_request} is not a Purchase request.",
            error_type="validation_error",
            user_message="只有 Purchase 类型的材料申请才能生成采购订单草稿。",
            data={
                "doctype": "Material Request",
                "name": material_request,
                "material_request_type": material_request_type,
                "status": "Unsupported Material Request Type",
                "summary": "Use a Purchase Material Request for Purchase Order creation.",
                "next_actions": ["choose_purchase_material_request"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    return None


def _material_request_purchase_order_context(doc: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    source_rows = [row for row in doc.get("items") or [] if isinstance(row, dict)]
    requests = [row for row in args.get("selected_items") or [] if isinstance(row, dict)]
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    if requests:
        selected_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for request in requests:
            matches = _match_material_request_rows(source_rows, request)
            if not matches:
                errors.append({"type": "row_not_found", "request": request, "message": "No Material Request item row matched this request."})
                continue
            if len(matches) > 1:
                errors.append({"type": "ambiguous_row", "request": request, "message": "Multiple Material Request rows matched; provide material_request_item."})
                continue
            selected_rows.append((matches[0], request))
    else:
        selected_rows = [(row, {}) for row in source_rows]

    remaining_by_row: dict[str, float] = {}
    for index, (row, request) in enumerate(selected_rows):
        row_key = str(row.get("name") or f"row-{index}")
        remaining_qty = remaining_by_row.setdefault(row_key, _material_request_remaining_qty(row))
        if remaining_qty <= 0:
            warnings.append(
                {
                    "type": "fully_ordered_row_skipped",
                    "material_request_item": row.get("name"),
                    "item_code": row.get("item_code"),
                    "message": "Material Request row has no remaining quantity to order.",
                }
            )
            continue
        requested_qty = _float_or_none(request.get("qty")) if request else None
        order_qty = requested_qty if requested_qty is not None else remaining_qty
        if order_qty <= 0:
            errors.append({"type": "invalid_qty", "request": request, "message": "Requested Purchase Order quantity must be greater than zero."})
            continue
        if order_qty > remaining_qty:
            errors.append(
                {
                    "type": "qty_exceeds_remaining",
                    "material_request_item": row.get("name"),
                    "item_code": row.get("item_code"),
                    "requested_qty": order_qty,
                    "remaining_qty": remaining_qty,
                }
            )
            continue
        if not row.get("item_code"):
            errors.append({"type": "missing_item_code", "material_request_item": row.get("name"), "message": "Material Request row has no item_code."})
            continue
        items.append(_purchase_order_item_from_material_request_row(row, request, order_qty, doc, args))
        remaining_by_row[row_key] = remaining_qty - order_qty

    return {
        "material_request": doc.get("name"),
        "default_schedule_date": args.get("schedule_date") or doc.get("schedule_date"),
        "items": items,
        "warnings": warnings,
        "errors": errors,
        "source_row_count": len(source_rows),
        "selected_row_count": len(selected_rows),
    }


def _match_material_request_rows(rows: list[dict[str, Any]], request: dict[str, Any]) -> list[dict[str, Any]]:
    if request.get("material_request_item"):
        return [row for row in rows if row.get("name") == request["material_request_item"]]
    if request.get("item_code"):
        return [row for row in rows if row.get("item_code") == request["item_code"]]
    return []


def _material_request_remaining_qty(row: dict[str, Any]) -> float:
    qty = _float_or_none(row.get("qty")) or 0.0
    ordered_qty = _float_or_none(row.get("ordered_qty")) or 0.0
    return max(qty - ordered_qty, 0.0)


def _purchase_order_item_from_material_request_row(
    row: dict[str, Any],
    request: dict[str, Any],
    qty: float,
    doc: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return _without_empty(
        {
            "item_code": row.get("item_code"),
            "qty": qty,
            "uom": row.get("uom") or row.get("stock_uom"),
            "schedule_date": request.get("schedule_date") or args.get("schedule_date") or row.get("schedule_date") or doc.get("schedule_date"),
            "warehouse": request.get("warehouse") or row.get("warehouse"),
            "rate": request.get("rate") if request.get("rate") is not None else row.get("rate"),
            "description": row.get("description"),
            "material_request": doc.get("name"),
            "material_request_item": row.get("name"),
            "project": row.get("project") or doc.get("project"),
            "cost_center": row.get("cost_center") or doc.get("cost_center"),
        }
    )


def _validate_purchase_order_for_purchase_receipt(doc: dict[str, Any], purchase_order: str) -> ToolResult | None:
    if doc.get("docstatus") != 1:
        return ToolResult(
            ok=False,
            error=f"Purchase Order {purchase_order} is not submitted.",
            error_type="validation_error",
            user_message="只有已提交的采购订单才能生成采购收货草稿。",
            data={
                "doctype": "Purchase Order",
                "name": purchase_order,
                "docstatus": doc.get("docstatus"),
                "status": "Not Submitted",
                "summary": "Submit the Purchase Order before creating a Purchase Receipt from it.",
                "next_actions": ["submit_purchase_order", "retry_purchase_receipt_creation"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    if str(doc.get("status") or "").lower() in {"closed", "cancelled"}:
        return ToolResult(
            ok=False,
            error=f"Purchase Order {purchase_order} is not open for receiving.",
            error_type="validation_error",
            user_message="该采购订单已关闭或取消，不能生成采购收货草稿。",
            data={
                "doctype": "Purchase Order",
                "name": purchase_order,
                "status": doc.get("status"),
                "summary": "Choose an open submitted Purchase Order.",
                "next_actions": ["choose_open_purchase_order"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    return None


def _purchase_order_receipt_context(doc: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    source_rows = [row for row in doc.get("items") or [] if isinstance(row, dict)]
    requests = [row for row in args.get("selected_items") or [] if isinstance(row, dict)]
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    if requests:
        selected_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for request in requests:
            matches = _match_purchase_order_rows(source_rows, request)
            if not matches:
                errors.append({"type": "row_not_found", "request": request, "message": "No Purchase Order item row matched this request."})
                continue
            if len(matches) > 1:
                errors.append({"type": "ambiguous_row", "request": request, "message": "Multiple Purchase Order rows matched; provide purchase_order_item."})
                continue
            selected_rows.append((matches[0], request))
    else:
        selected_rows = [(row, {}) for row in source_rows]

    remaining_by_row: dict[str, float] = {}
    for index, (row, request) in enumerate(selected_rows):
        row_key = str(row.get("name") or f"row-{index}")
        remaining_qty = remaining_by_row.setdefault(row_key, _purchase_order_remaining_receipt_qty(row))
        if remaining_qty <= 0:
            warnings.append(
                {
                    "type": "fully_received_row_skipped",
                    "purchase_order_item": row.get("name"),
                    "item_code": row.get("item_code"),
                    "message": "Purchase Order row has no remaining quantity to receive.",
                }
            )
            continue
        requested_qty = _float_or_none(request.get("qty")) if request else None
        receipt_qty = requested_qty if requested_qty is not None else remaining_qty
        if receipt_qty <= 0:
            errors.append({"type": "invalid_qty", "request": request, "message": "Requested Purchase Receipt quantity must be greater than zero."})
            continue
        if receipt_qty > remaining_qty:
            errors.append(
                {
                    "type": "qty_exceeds_remaining",
                    "purchase_order_item": row.get("name"),
                    "item_code": row.get("item_code"),
                    "requested_qty": receipt_qty,
                    "remaining_qty": remaining_qty,
                }
            )
            continue
        if not row.get("item_code"):
            errors.append({"type": "missing_item_code", "purchase_order_item": row.get("name"), "message": "Purchase Order row has no item_code."})
            continue
        items.append(_purchase_receipt_item_from_purchase_order_row(row, request, receipt_qty, doc))
        remaining_by_row[row_key] = remaining_qty - receipt_qty

    return {
        "purchase_order": doc.get("name"),
        "items": items,
        "warnings": warnings,
        "errors": errors,
        "source_row_count": len(source_rows),
        "selected_row_count": len(selected_rows),
    }


def _match_purchase_order_rows(rows: list[dict[str, Any]], request: dict[str, Any]) -> list[dict[str, Any]]:
    if request.get("purchase_order_item"):
        return [row for row in rows if row.get("name") == request["purchase_order_item"]]
    if request.get("item_code"):
        return [row for row in rows if row.get("item_code") == request["item_code"]]
    return []


def _purchase_order_remaining_receipt_qty(row: dict[str, Any]) -> float:
    qty = _float_or_none(row.get("qty")) or 0.0
    received_qty = _float_or_none(row.get("received_qty")) or 0.0
    return max(qty - received_qty, 0.0)


def _purchase_receipt_item_from_purchase_order_row(
    row: dict[str, Any],
    request: dict[str, Any],
    qty: float,
    doc: dict[str, Any],
) -> dict[str, Any]:
    return _without_empty(
        {
            "item_code": row.get("item_code"),
            "qty": qty,
            "uom": row.get("uom") or row.get("stock_uom"),
            "warehouse": request.get("warehouse") or row.get("warehouse"),
            "rate": row.get("rate"),
            "price_list_rate": row.get("price_list_rate"),
            "conversion_factor": row.get("conversion_factor"),
            "description": row.get("description"),
            "purchase_order": doc.get("name"),
            "purchase_order_item": row.get("name"),
            "project": row.get("project") or doc.get("project"),
            "cost_center": row.get("cost_center") or doc.get("cost_center"),
        }
    )


def _purchase_receipt_discrepancy_summary(args: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": args.get("discrepancy_type") or "spec_mismatch",
        "severity": args.get("severity") or "Medium",
        "description": args["description"],
        "reported_by": args.get("reported_by"),
        "item_count": len(items),
    }


def _purchase_receipt_discrepancy_comment(
    purchase_receipt: str,
    discrepancy: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    lines = [
        "Agent 到货差异记录",
        f"采购收货单: {purchase_receipt}",
        f"类型: {discrepancy['type']}",
        f"严重度: {discrepancy['severity']}",
    ]
    if discrepancy.get("reported_by"):
        lines.append(f"报告人: {discrepancy['reported_by']}")
    lines.append(f"说明: {discrepancy['description']}")
    if items:
        lines.append("涉及明细:")
        for index, item in enumerate(items, start=1):
            parts = [
                f"{index}.",
                str(item.get("item_code") or item.get("purchase_receipt_item") or "未指定物料"),
            ]
            if item.get("qty") is not None:
                parts.append(f"数量 {item['qty']}")
            if item.get("expected"):
                parts.append(f"应为: {item['expected']}")
            if item.get("actual"):
                parts.append(f"实到: {item['actual']}")
            if item.get("reason"):
                parts.append(f"原因: {item['reason']}")
            lines.append("；".join(parts))
    return "\n".join(lines)


def _purchase_receipt_discrepancy_todo_description(purchase_receipt: str, discrepancy: dict[str, Any]) -> str:
    return f"跟进采购收货 {purchase_receipt} 到货差异：{discrepancy['description']}"


def _priority_from_severity(severity: str) -> str:
    normalized = severity.strip().lower()
    if normalized in {"critical", "high", "严重", "高"}:
        return "High"
    if normalized in {"low", "minor", "低", "轻微"}:
        return "Low"
    return "Medium"


def _purchase_receipt_discrepancy_return_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests = []
    for item in items:
        if item.get("qty") is None:
            continue
        requests.append(
            _without_empty(
                {
                    "purchase_receipt_item": item.get("purchase_receipt_item"),
                    "item_code": item.get("item_code"),
                    "warehouse": item.get("warehouse"),
                    "qty": item.get("qty"),
                    "reason": item.get("reason"),
                }
            )
        )
    return requests


def _validate_purchase_receipt_can_return(doc: dict[str, Any], purchase_receipt: str) -> ToolResult | None:
    if doc.get("docstatus") != 1:
        return ToolResult(
            ok=False,
            error=f"Purchase Receipt {purchase_receipt} is not submitted.",
            error_type="validation_error",
            user_message="只有已提交的采购收货单才能创建采购退货。",
            data={
                "doctype": "Purchase Receipt",
                "name": purchase_receipt,
                "docstatus": doc.get("docstatus"),
                "status": "Not Submitted",
                "summary": "Submit the original Purchase Receipt before creating a return.",
                "next_actions": ["submit_purchase_receipt", "retry_return_context"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    if _truthy(doc.get("is_return")):
        return ToolResult(
            ok=False,
            error=f"Purchase Receipt {purchase_receipt} is already a return document.",
            error_type="validation_error",
            user_message="这张采购收货单本身已经是退货单，不能再作为原始收货创建退货。",
            data={
                "doctype": "Purchase Receipt",
                "name": purchase_receipt,
                "status": "Already Return",
                "summary": "Return documents cannot be returned again through this helper.",
                "next_actions": ["choose_original_purchase_receipt"],
                "risk": {"level": "L1", "requires_confirmation_for_submit": False},
            },
        )
    return None


def _purchase_receipt_return_context(doc: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in doc.get("items") or [] if isinstance(row, dict)]
    requests = [row for row in args.get("items") or [] if isinstance(row, dict)]
    full_return = bool(args.get("full_return")) or not requests
    remaining_by_key = {
        _purchase_receipt_row_key(row, index): _purchase_receipt_returnable_qty(row)
        for index, row in enumerate(rows)
    }
    return_items: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if full_return:
        for index, row in enumerate(rows):
            row_key = _purchase_receipt_row_key(row, index)
            qty = remaining_by_key.get(row_key, 0.0)
            if qty <= 0:
                continue
            return_items.append(_purchase_receipt_return_item(row, qty, args.get("reason")))
            remaining_by_key[row_key] = 0.0
        if not return_items:
            warnings.append({"type": "no_returnable_rows", "message": "No returnable Purchase Receipt item rows were found."})
        return {"return_items": return_items, "warnings": warnings, "errors": errors}

    for request in requests:
        matches = _match_purchase_receipt_rows(rows, request)
        if not matches:
            errors.append({"type": "row_not_found", "request": request, "message": "No Purchase Receipt item row matched this return request."})
            continue

        requested_qty = _float_or_none(request.get("qty"))
        remaining_request_qty = requested_qty
        request_added = 0.0
        for index, row in matches:
            row_key = _purchase_receipt_row_key(row, index)
            row_remaining = remaining_by_key.get(row_key, 0.0)
            if row_remaining <= 0:
                continue
            qty = row_remaining if remaining_request_qty is None else min(row_remaining, remaining_request_qty)
            if qty <= 0:
                continue
            return_items.append(_purchase_receipt_return_item(row, qty, request.get("reason") or args.get("reason"), request))
            remaining_by_key[row_key] = row_remaining - qty
            request_added += qty
            if remaining_request_qty is not None:
                remaining_request_qty -= qty
                if remaining_request_qty <= 0:
                    break

        if request_added <= 0:
            errors.append({"type": "no_returnable_qty", "request": request, "message": "Matched rows have no remaining returnable quantity."})
        elif requested_qty is not None and remaining_request_qty and remaining_request_qty > 0:
            errors.append(
                {
                    "type": "qty_exceeds_returnable",
                    "request": request,
                    "requested_qty": requested_qty,
                    "allocated_qty": request_added,
                    "short_qty": remaining_request_qty,
                    "message": "Requested return quantity exceeds remaining returnable quantity.",
                }
            )

    return {"return_items": return_items, "warnings": warnings, "errors": errors}


def _match_purchase_receipt_rows(rows: list[dict[str, Any]], request: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    purchase_receipt_item = request.get("purchase_receipt_item")
    item_code = request.get("item_code")
    warehouse = request.get("warehouse")
    matches = []
    for index, row in enumerate(rows):
        if purchase_receipt_item and row.get("name") != purchase_receipt_item:
            continue
        if item_code and row.get("item_code") != item_code:
            continue
        if warehouse and row.get("warehouse") != warehouse:
            continue
        if not purchase_receipt_item and not item_code:
            continue
        matches.append((index, row))
    return matches


def _purchase_receipt_row_key(row: dict[str, Any], index: int) -> str:
    return str(row.get("name") or f"row-{index}")


def _purchase_receipt_returnable_qty(row: dict[str, Any]) -> float:
    original_qty = _first_float(row, ("received_qty", "qty", "stock_qty")) or 0.0
    returned_qty = _float_or_none(row.get("returned_qty")) or 0.0
    return max(original_qty - returned_qty, 0.0)


def _purchase_receipt_return_item(
    row: dict[str, Any],
    qty: float,
    reason: str | None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request or {}
    return _clean_mapping(
        {
            "purchase_receipt_item": row.get("name"),
            "item_code": row.get("item_code"),
            "item_name": row.get("item_name"),
            "requested_qty": qty,
            "return_qty": -qty,
            "returnable_qty_before_request": _purchase_receipt_returnable_qty(row),
            "warehouse": request.get("warehouse") or row.get("warehouse"),
            "uom": row.get("uom"),
            "stock_uom": row.get("stock_uom"),
            "conversion_factor": row.get("conversion_factor"),
            "rate": _first_float(row, ("rate", "base_rate", "net_rate")),
            "price_list_rate": _float_or_none(row.get("price_list_rate")),
            "purchase_order": row.get("purchase_order"),
            "purchase_order_item": row.get("purchase_order_item"),
            "project": row.get("project"),
            "cost_center": row.get("cost_center"),
            "expense_account": row.get("expense_account"),
            "description": row.get("description"),
            "reason": reason,
        }
    )


def _purchase_receipt_return_draft_item(row: dict[str, Any], default_reason: str | None) -> dict[str, Any]:
    reason = row.get("reason") or default_reason
    description = row.get("description")
    if reason:
        description = f"{description or row.get('item_name') or row.get('item_code')} | Return reason: {reason}"
    return _without_empty(
        {
            "item_code": row.get("item_code"),
            "item_name": row.get("item_name"),
            "qty": row.get("return_qty"),
            "received_qty": row.get("return_qty"),
            "uom": row.get("uom"),
            "stock_uom": row.get("stock_uom"),
            "conversion_factor": row.get("conversion_factor"),
            "warehouse": row.get("warehouse"),
            "rate": row.get("rate"),
            "price_list_rate": row.get("price_list_rate"),
            "purchase_receipt_item": row.get("purchase_receipt_item"),
            "purchase_order": row.get("purchase_order"),
            "purchase_order_item": row.get("purchase_order_item"),
            "project": row.get("project"),
            "cost_center": row.get("cost_center"),
            "expense_account": row.get("expense_account"),
            "description": description,
        }
    )
