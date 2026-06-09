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
