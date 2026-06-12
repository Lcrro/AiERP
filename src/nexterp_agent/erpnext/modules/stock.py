from __future__ import annotations

from typing import Any

from nexterp_agent.item_master import MaterialSearch, PostgresCatalogSearchClient

from ..schemas import ToolResult
from .common import *

class StockToolsMixin:
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

    def _stock_create_quality_inspection_draft(self, args: dict[str, Any]) -> ToolResult:
        data = dict(args)
        if not data.get("item_code"):
            data["item_code"] = self._stock_item_code_from_args(data)
        if not data.get("item_code"):
            return _item_resolution_error("质量检验草稿中无法解析 item_code。")

        data = _without_empty(
            {
                "doctype": "Quality Inspection",
                "item_code": data.get("item_code"),
                "inspection_type": data.get("inspection_type") or "Incoming",
                "reference_type": data.get("reference_type"),
                "reference_name": data.get("reference_name"),
                "sample_size": data.get("sample_size"),
                "inspected_by": data.get("inspected_by"),
                "verified_by": data.get("verified_by"),
                "report_date": data.get("report_date"),
                "status": data.get("status"),
                "remarks": data.get("remarks"),
                "readings": [_quality_inspection_reading(row) for row in data.get("readings") or [] if isinstance(row, dict)],
                "docstatus": 0,
            }
        )
        result = self.client.create_document("Quality Inspection", data)
        if not result.ok:
            return result
        raw = result.data if isinstance(result.data, dict) else {}
        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data={
                "doctype": "Quality Inspection",
                "name": raw.get("name"),
                "docstatus": raw.get("docstatus", 0),
                "status": "Draft",
                "summary": f"Created Quality Inspection draft for Item {data.get('item_code')}.",
                "item_code": data.get("item_code"),
                "reference": _clean_mapping({"reference_type": data.get("reference_type"), "reference_name": data.get("reference_name")}),
                "reading_count": len(data.get("readings") or []),
                "next_actions": ["review_quality_inspection_draft", "record_purchase_receipt_discrepancy_if_failed"],
                "risk": {"level": "L3", "requires_confirmation_for_submit": False, "does_not_move_stock": True},
            },
            debug={"raw_document": raw},
        )

    def _stock_verify_purchase_receipt_stock_impact(self, args: dict[str, Any]) -> ToolResult:
        purchase_receipt = args["purchase_receipt"]
        document = self.client.get_document("Purchase Receipt", purchase_receipt)
        if not document.ok:
            return document
        doc = document.data if isinstance(document.data, dict) else {}
        ledger = self.client.get_stock_ledger_entries(
            voucher_type="Purchase Receipt",
            voucher_no=purchase_receipt,
            limit=args.get("limit", 200),
        )
        if not ledger.ok:
            return ledger
        ledger_rows = [row for row in (ledger.data if isinstance(ledger.data, list) else []) if isinstance(row, dict)]
        if args.get("item_code"):
            ledger_rows = [row for row in ledger_rows if row.get("item_code") == args["item_code"]]
        if args.get("warehouse"):
            ledger_rows = [row for row in ledger_rows if row.get("warehouse") == args["warehouse"]]

        item_rows = _purchase_receipt_expected_stock_rows(doc, item_code=args.get("item_code"), warehouse=args.get("warehouse"))
        matches = _match_expected_rows_to_ledger(item_rows, ledger_rows)
        warnings = _purchase_receipt_stock_warnings(doc, item_rows, ledger_rows, matches)
        status = "Verified" if doc.get("docstatus") == 1 and not warnings else "Review Required"
        total_expected_qty = sum(_float_or_none(row.get("expected_stock_qty")) or 0.0 for row in item_rows)
        total_ledger_qty = sum(_float_or_none(row.get("ledger_actual_qty")) or 0.0 for row in matches)
        total_ledger_value = sum(_float_or_none(row.get("ledger_stock_value_difference")) or 0.0 for row in matches)
        return ToolResult(
            ok=True,
            status_code=document.status_code,
            raw_status_code=document.raw_status_code,
            data={
                "doctype": "Purchase Receipt",
                "name": purchase_receipt,
                "docstatus": doc.get("docstatus"),
                "status": status,
                "summary": (
                    f"Verified Purchase Receipt {purchase_receipt}: "
                    f"{len(item_rows)} expected row(s), {len(ledger_rows)} stock ledger row(s)."
                ),
                "supplier": doc.get("supplier"),
                "posting_date": doc.get("posting_date"),
                "totals": {
                    "expected_stock_qty": round(total_expected_qty, 6),
                    "ledger_actual_qty": round(total_ledger_qty, 6),
                    "ledger_stock_value_difference": round(total_ledger_value, 2),
                },
                "rows": matches,
                "warnings": warnings,
                "next_actions": ["review_purchase_receipt_stock_impact"] if warnings else ["create_purchase_invoice_from_purchase_receipt_draft", "issue_material_to_project_when_needed"],
                "risk": {"level": "L0", "writes_document": False, "moves_stock": False},
            },
            debug={"raw_purchase_receipt": doc, "raw_stock_ledger_entries": ledger_rows},
        )

    def _stock_get_item_lifecycle_summary(self, args: dict[str, Any]) -> ToolResult:
        item_code = self._stock_item_code_from_args(args)
        if not item_code:
            return _item_resolution_error("物料生命周期摘要中无法解析 item_code。")

        limit = args.get("limit", 50)
        item_result = self.client.get_document("Item", item_code)
        if not item_result.ok:
            return item_result

        purchase_receipt_items = self.client.search_documents(
            "Purchase Receipt Item",
            filters=_item_child_filters(args, item_code, warehouse_field="warehouse", project_field="project"),
            fields=["name", "parent", "item_code", "item_name", "qty", "received_qty", "warehouse", "project", "rate", "amount"],
            limit=limit,
            order_by="modified desc",
        )
        if not purchase_receipt_items.ok:
            return purchase_receipt_items

        quality_inspections = self.client.list_quality_inspections(
            item_code=item_code,
            reference_type=args.get("reference_type"),
            reference_name=args.get("reference_name"),
            limit=limit,
        )
        if not quality_inspections.ok:
            return quality_inspections

        ledger_filters = _stock_ledger_lifecycle_filters(args, item_code)
        stock_ledger = self.client.search_documents(
            "Stock Ledger Entry",
            filters=ledger_filters,
            fields=[
                "name",
                "item_code",
                "warehouse",
                "posting_date",
                "posting_time",
                "voucher_type",
                "voucher_no",
                "actual_qty",
                "qty_after_transaction",
                "valuation_rate",
                "stock_value_difference",
                "stock_value",
                "is_cancelled",
            ],
            limit=limit,
            order_by="posting_date desc, posting_time desc, creation desc",
        )
        if not stock_ledger.ok:
            return stock_ledger

        stock_entry_details = self.client.search_documents(
            "Stock Entry Detail",
            filters=_stock_entry_detail_lifecycle_filters(args, item_code),
            fields=["name", "parent", "item_code", "qty", "s_warehouse", "t_warehouse", "project", "cost_center", "basic_rate", "basic_amount"],
            limit=limit,
            order_by="modified desc",
        )
        if not stock_entry_details.ok:
            return stock_entry_details

        purchase_invoice_items = self.client.search_documents(
            "Purchase Invoice Item",
            filters=_item_child_filters(args, item_code, project_field="project"),
            fields=["name", "parent", "item_code", "item_name", "qty", "purchase_receipt", "pr_detail", "purchase_order", "po_detail", "project", "rate", "amount"],
            limit=limit,
            order_by="modified desc",
        )
        if not purchase_invoice_items.ok:
            return purchase_invoice_items

        item = item_result.data if isinstance(item_result.data, dict) else {}
        pr_rows = purchase_receipt_items.data if isinstance(purchase_receipt_items.data, list) else []
        qi_rows = quality_inspections.data if isinstance(quality_inspections.data, list) else []
        sle_rows = stock_ledger.data if isinstance(stock_ledger.data, list) else []
        se_rows = stock_entry_details.data if isinstance(stock_entry_details.data, list) else []
        pi_rows = purchase_invoice_items.data if isinstance(purchase_invoice_items.data, list) else []
        totals = _item_lifecycle_totals(pr_rows, sle_rows, se_rows, pi_rows)
        return ToolResult(
            ok=True,
            status_code=item_result.status_code,
            raw_status_code=item_result.raw_status_code,
            data={
                "doctype": "Item",
                "name": item_code,
                "status": "Lifecycle Summary Ready",
                "summary": (
                    f"Prepared lifecycle summary for Item {item_code}: "
                    f"{len(pr_rows)} receipt row(s), {len(sle_rows)} ledger row(s), "
                    f"{len(se_rows)} stock entry detail row(s), {len(qi_rows)} quality inspection row(s)."
                ),
                "item": _clean_mapping(
                    {
                        "item_code": item.get("item_code") or item_code,
                        "item_name": item.get("item_name"),
                        "item_group": item.get("item_group"),
                        "stock_uom": item.get("stock_uom"),
                        "disabled": item.get("disabled"),
                    }
                ),
                "filters": _clean_mapping(
                    {
                        "project": args.get("project"),
                        "warehouse": args.get("warehouse"),
                        "from_date": args.get("from_date"),
                        "to_date": args.get("to_date"),
                        "limit": limit,
                    }
                ),
                "totals": totals,
                "purchase_receipt_items": pr_rows,
                "quality_inspections": qi_rows,
                "stock_ledger_entries": sle_rows,
                "stock_entry_details": se_rows,
                "purchase_invoice_items": pi_rows,
                "next_actions": ["review_lifecycle_summary", "verify_stock_or_project_cost_impact"],
                "risk": {"level": "L0", "writes_document": False},
            },
            debug={"raw_item": item},
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


def _quality_inspection_reading(row: dict[str, Any]) -> dict[str, Any]:
    return _without_empty(
        {
            "specification": row.get("specification"),
            "value": row.get("value"),
            "status": row.get("status"),
            "numeric_value": row.get("numeric_value"),
            "min_value": row.get("min_value"),
            "max_value": row.get("max_value"),
        }
    )


def _purchase_receipt_expected_stock_rows(
    doc: dict[str, Any],
    *,
    item_code: str | None = None,
    warehouse: str | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for row in doc.get("items") or []:
        if not isinstance(row, dict):
            continue
        row_item = row.get("item_code")
        row_warehouse = row.get("warehouse")
        if item_code and row_item != item_code:
            continue
        if warehouse and row_warehouse != warehouse:
            continue
        key = (row_item, row_warehouse)
        bucket = grouped.setdefault(
            key,
            {
                "item_code": row_item,
                "item_name": row.get("item_name"),
                "warehouse": row_warehouse,
                "uom": row.get("stock_uom") or row.get("uom"),
                "expected_stock_qty": 0.0,
                "accepted_qty": 0.0,
                "rejected_qty": 0.0,
                "amount": 0.0,
                "source_rows": [],
            },
        )
        stock_qty = _first_float(row, ("stock_qty", "received_stock_qty", "received_qty", "qty")) or 0.0
        rejected_qty = _float_or_none(row.get("rejected_qty")) or 0.0
        bucket["expected_stock_qty"] += stock_qty
        bucket["accepted_qty"] += max(stock_qty - rejected_qty, 0.0)
        bucket["rejected_qty"] += rejected_qty
        bucket["amount"] += _first_float(row, ("base_net_amount", "net_amount", "base_amount", "amount")) or 0.0
        bucket["source_rows"].append(
            _clean_mapping(
                {
                    "name": row.get("name"),
                    "item_code": row_item,
                    "warehouse": row_warehouse,
                    "qty": row.get("qty"),
                    "stock_qty": row.get("stock_qty"),
                    "received_qty": row.get("received_qty"),
                    "rejected_qty": row.get("rejected_qty"),
                    "purchase_order": row.get("purchase_order"),
                    "purchase_order_item": row.get("purchase_order_item"),
                    "project": row.get("project"),
                }
            )
        )
    return [_round_stock_row(row) for row in grouped.values()]


def _match_expected_rows_to_ledger(expected_rows: list[dict[str, Any]], ledger_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledger_by_key: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for row in ledger_rows:
        key = (row.get("item_code"), row.get("warehouse"))
        bucket = ledger_by_key.setdefault(
            key,
            {
                "ledger_actual_qty": 0.0,
                "ledger_stock_value_difference": 0.0,
                "ledger_entry_count": 0,
                "ledger_entries": [],
            },
        )
        bucket["ledger_actual_qty"] += _float_or_none(row.get("actual_qty")) or 0.0
        bucket["ledger_stock_value_difference"] += _first_float(row, ("stock_value_difference", "stock_value")) or 0.0
        bucket["ledger_entry_count"] += 1
        bucket["ledger_entries"].append(row)

    matches = []
    for expected in expected_rows:
        key = (expected.get("item_code"), expected.get("warehouse"))
        ledger = ledger_by_key.get(key, {"ledger_actual_qty": 0.0, "ledger_stock_value_difference": 0.0, "ledger_entry_count": 0, "ledger_entries": []})
        delta = (_float_or_none(ledger.get("ledger_actual_qty")) or 0.0) - (_float_or_none(expected.get("expected_stock_qty")) or 0.0)
        matches.append(
            {
                **expected,
                "ledger_actual_qty": round(_float_or_none(ledger.get("ledger_actual_qty")) or 0.0, 6),
                "ledger_stock_value_difference": round(_float_or_none(ledger.get("ledger_stock_value_difference")) or 0.0, 2),
                "ledger_entry_count": ledger.get("ledger_entry_count") or 0,
                "qty_delta": round(delta, 6),
                "matched": abs(delta) < 0.000001 and bool(ledger.get("ledger_entry_count")),
            }
        )
    return matches


def _purchase_receipt_stock_warnings(
    doc: dict[str, Any],
    expected_rows: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings = []
    if doc.get("docstatus") != 1:
        warnings.append({"type": "not_submitted", "message": "Purchase Receipt is not submitted, so stock ledger impact may not exist yet."})
    if not expected_rows:
        warnings.append({"type": "no_expected_rows", "message": "No Purchase Receipt item rows matched the supplied filters."})
    if doc.get("docstatus") == 1 and not ledger_rows:
        warnings.append({"type": "no_stock_ledger_entries", "message": "Submitted Purchase Receipt has no matching Stock Ledger Entry rows."})
    mismatches = [row for row in matches if row.get("ledger_entry_count") and abs(_float_or_none(row.get("qty_delta")) or 0.0) >= 0.000001]
    if mismatches:
        warnings.append({"type": "quantity_mismatch", "message": "Expected receipt quantity does not match Stock Ledger Entry actual quantity.", "rows": mismatches})
    return warnings


def _round_stock_row(row: dict[str, Any]) -> dict[str, Any]:
    rounded = dict(row)
    for key in ("expected_stock_qty", "accepted_qty", "rejected_qty", "amount"):
        if key in rounded:
            rounded[key] = round(_float_or_none(rounded.get(key)) or 0.0, 6 if key.endswith("qty") else 2)
    return rounded


def _item_child_filters(
    args: dict[str, Any],
    item_code: str,
    *,
    warehouse_field: str | None = None,
    project_field: str | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {"item_code": item_code}
    if warehouse_field and args.get("warehouse"):
        filters[warehouse_field] = args["warehouse"]
    if project_field and args.get("project"):
        filters[project_field] = args["project"]
    return filters


def _stock_ledger_lifecycle_filters(args: dict[str, Any], item_code: str) -> dict[str, Any]:
    filters: dict[str, Any] = {"item_code": item_code, "is_cancelled": 0}
    if args.get("warehouse"):
        filters["warehouse"] = args["warehouse"]
    if args.get("from_date") and args.get("to_date"):
        filters["posting_date"] = ["between", [args["from_date"], args["to_date"]]]
    elif args.get("from_date"):
        filters["posting_date"] = [">=", args["from_date"]]
    elif args.get("to_date"):
        filters["posting_date"] = ["<=", args["to_date"]]
    return filters


def _stock_entry_detail_lifecycle_filters(args: dict[str, Any], item_code: str) -> dict[str, Any]:
    filters: dict[str, Any] = {"item_code": item_code}
    if args.get("project"):
        filters["project"] = args["project"]
    if args.get("warehouse"):
        filters["s_warehouse"] = args["warehouse"]
    return filters


def _item_lifecycle_totals(
    purchase_receipt_items: list[dict[str, Any]],
    stock_ledger_entries: list[dict[str, Any]],
    stock_entry_details: list[dict[str, Any]],
    purchase_invoice_items: list[dict[str, Any]],
) -> dict[str, Any]:
    receipt_qty = sum(_first_float(row, ("stock_qty", "received_qty", "qty")) or 0.0 for row in purchase_receipt_items if isinstance(row, dict))
    ledger_in_qty = sum(max(_float_or_none(row.get("actual_qty")) or 0.0, 0.0) for row in stock_ledger_entries if isinstance(row, dict))
    ledger_out_qty = abs(sum(min(_float_or_none(row.get("actual_qty")) or 0.0, 0.0) for row in stock_ledger_entries if isinstance(row, dict)))
    ledger_value = sum(_first_float(row, ("stock_value_difference", "stock_value")) or 0.0 for row in stock_ledger_entries if isinstance(row, dict))
    project_issue_qty = sum(_float_or_none(row.get("qty")) or 0.0 for row in stock_entry_details if isinstance(row, dict) and row.get("s_warehouse"))
    project_issue_amount = sum(_first_float(row, ("basic_amount", "amount")) or 0.0 for row in stock_entry_details if isinstance(row, dict) and row.get("s_warehouse"))
    invoiced_qty = sum(_float_or_none(row.get("qty")) or 0.0 for row in purchase_invoice_items if isinstance(row, dict))
    invoiced_amount = sum(_first_float(row, ("base_net_amount", "net_amount", "base_amount", "amount")) or 0.0 for row in purchase_invoice_items if isinstance(row, dict))
    return {
        "purchase_receipt_qty": round(receipt_qty, 6),
        "ledger_in_qty": round(ledger_in_qty, 6),
        "ledger_out_qty": round(ledger_out_qty, 6),
        "ledger_net_qty": round(ledger_in_qty - ledger_out_qty, 6),
        "ledger_value_difference": round(ledger_value, 2),
        "project_issue_qty": round(project_issue_qty, 6),
        "project_issue_amount": round(project_issue_amount, 2),
        "purchase_invoice_qty": round(invoiced_qty, 6),
        "purchase_invoice_amount": round(invoiced_amount, 2),
    }
