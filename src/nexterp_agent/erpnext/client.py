from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from .schemas import ToolResult


class ERPNextClient:
    """Thin HTTP client for Frappe/ERPNext APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        *,
        host_header: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"token {api_key}:{api_secret}",
            }
        )
        if host_header:
            self.session.headers.update({"Host": host_header})

    def request(self, method: str, path: str, **kwargs: Any) -> ToolResult:
        kwargs.setdefault("headers", {"Content-Type": "application/json"})
        try:
            response = self.session.request(
                method,
                self.base_url + path,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            return ToolResult(
                ok=False,
                error=str(exc),
                error_type="network_error",
                user_message="无法连接 ERPNext，请检查网络或服务状态。",
            )

        payload = _parse_json_response(response)
        if not response.ok:
            error = _extract_error(payload)
            return ToolResult(
                ok=False,
                status_code=response.status_code,
                raw_status_code=response.status_code,
                error=error,
                error_type=classify_error(response.status_code, payload, error),
                user_message=build_user_message(response.status_code, payload, error),
                data=payload,
                debug={"raw_response": payload},
            )

        return ToolResult(
            ok=True,
            status_code=response.status_code,
            raw_status_code=response.status_code,
            data=_extract_data(payload),
        )

    def get_logged_user(self) -> ToolResult:
        return self.request("GET", "/api/method/frappe.auth.get_logged_user")

    def search_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
    ) -> ToolResult:
        params: dict[str, Any] = {
            "limit_page_length": limit,
            "limit_start": offset,
        }
        if filters:
            params["filters"] = json.dumps(normalize_filters(filters))
        if fields:
            params["fields"] = json.dumps(fields)
        if order_by:
            params["order_by"] = order_by

        return self.request(
            "GET",
            f"/api/resource/{quote(doctype, safe='')}",
            params=params,
        )

    def get_document(self, doctype: str, name: str) -> ToolResult:
        return self.request(
            "GET",
            f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
        )

    def create_document(self, doctype: str, data: dict[str, Any]) -> ToolResult:
        return self.request(
            "POST",
            f"/api/resource/{quote(doctype, safe='')}",
            json=data,
        )

    def update_document(
        self,
        doctype: str,
        name: str,
        data: dict[str, Any],
    ) -> ToolResult:
        return self.request(
            "PUT",
            f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            json=data,
        )

    def delete_document(self, doctype: str, name: str) -> ToolResult:
        return self.request(
            "DELETE",
            f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
        )

    def count_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[Any] | None = None,
    ) -> ToolResult:
        args: dict[str, Any] = {"doctype": doctype}
        if filters:
            args["filters"] = normalize_filters(filters)
        return self.call_method("frappe.client.get_count", args)

    def document_exists(self, doctype: str, name: str) -> ToolResult:
        result = self.get_document(doctype, name)
        if result.ok:
            return ToolResult(ok=True, status_code=result.status_code, data={"exists": True, "name": name})
        if result.error_type == "not_found" or result.status_code == 404:
            return ToolResult(ok=True, status_code=result.status_code, data={"exists": False, "name": name})
        return result

    def resolve_link(
        self,
        doctype: str,
        query: str,
        *,
        search_field: str = "name",
        limit: int = 10,
    ) -> ToolResult:
        fields = ["name"]
        if search_field != "name":
            fields.append(search_field)
        return self.search_documents(
            doctype,
            filters={search_field: ["like", f"%{query}%"]},
            fields=fields,
            limit=limit,
        )

    def validate_fields(self, doctype: str, fields: list[str]) -> ToolResult:
        schema = self.get_doctype_schema(doctype)
        if not schema.ok:
            return schema

        raw_fields = schema.data.get("fields", []) if isinstance(schema.data, dict) else []
        known = {
            field.get("fieldname")
            for field in raw_fields
            if isinstance(field, dict) and field.get("fieldname")
        }
        known.add("name")
        invalid = [field for field in fields if field not in known]
        return ToolResult(
            ok=not invalid,
            data={"doctype": doctype, "valid_fields": [field for field in fields if field in known], "invalid_fields": invalid},
            error=None if not invalid else f"Invalid fields for {doctype}: {', '.join(invalid)}",
            error_type=None if not invalid else "validation_error",
            user_message=None if not invalid else f"{doctype} 不存在这些字段：{', '.join(invalid)}",
        )

    def get_doctype_schema(self, doctype: str) -> ToolResult:
        result = self.request(
            "GET",
            f"/api/v2/doctype/{quote(doctype, safe='')}/meta",
        )
        if result.ok:
            return result

        return self.call_method(
            "frappe.desk.form.load.getdoctype",
            {"doctype": doctype, "with_parent": 1},
        )

    def call_method(
        self,
        method: str,
        args: dict[str, Any] | None = None,
        *,
        http_method: str = "POST",
    ) -> ToolResult:
        if http_method.upper() == "GET":
            return self.request("GET", f"/api/method/{method}", params=args or {})

        return self.request("POST", f"/api/method/{method}", json=args or {})

    def submit_document(self, doctype: str, name: str) -> ToolResult:
        return self.call_method(
            "agent_bridge.api.submit_document",
            {"doctype": doctype, "name": name},
        )

    def cancel_document(self, doctype: str, name: str) -> ToolResult:
        return self.call_method(
            "agent_bridge.api.cancel_document",
            {"doctype": doctype, "name": name},
        )

    def amend_document(self, doctype: str, name: str) -> ToolResult:
        return self.call_method(
            "frappe.client.make_amended_doc",
            {"doctype": doctype, "docname": name},
        )

    def get_workflow_actions(self, doctype: str, name: str) -> ToolResult:
        doc = self.get_document(doctype, name)
        if not doc.ok:
            return doc
        return self.call_method(
            "frappe.model.workflow.get_transitions",
            {"doc": doc.data},
        )

    def apply_workflow(self, doctype: str, name: str, action: str) -> ToolResult:
        doc = self.get_document(doctype, name)
        if not doc.ok:
            return doc
        return self.call_method(
            "frappe.model.workflow.apply_workflow",
            {"doc": doc.data, "action": action},
        )

    def run_report(
        self,
        report_name: str,
        *,
        filters: dict[str, Any] | None = None,
        ignore_prepared_report: bool = True,
    ) -> ToolResult:
        result = self.call_method(
            "frappe.desk.query_report.run",
            {
                "report_name": report_name,
                "filters": json.dumps(filters or {}),
                "ignore_prepared_report": ignore_prepared_report,
            },
        )
        if not result.ok or not isinstance(result.data, dict):
            return result
        data = result.data
        normalized = {
            "report_name": report_name,
            "columns": data.get("columns") or [],
            "rows": data.get("result") or data.get("data") or [],
            "message": data.get("message"),
            "chart": data.get("chart"),
            "summary": data.get("report_summary") or data.get("summary"),
            "raw": data,
        }
        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data=normalized,
        )

    def generate_purchase_suggestions(self, limit: int = 50) -> ToolResult:
        return self.call_method("agent_bridge.api.generate_purchase_suggestions", {"limit": limit})

    def preview_stock_valuation(self, items: list[dict[str, Any]]) -> ToolResult:
        return self.call_method("agent_bridge.api.preview_stock_valuation", {"items": items})

    def allocate_stock_shortages(self, items: list[dict[str, Any]]) -> ToolResult:
        return self.call_method("agent_bridge.api.allocate_stock_shortages", {"items": items})

    def check_user_permission(
        self,
        user: str,
        doctype: str,
        action: str,
        *,
        docname: str | None = None,
        debug: bool = False,
    ) -> ToolResult:
        args: dict[str, Any] = {
            "user": user,
            "doctype": doctype,
            "action": action,
        }
        if docname:
            args["docname"] = docname
        if debug:
            args["debug"] = True
        return self.call_method("agent_bridge.api.check_user_permission", args)

    def create_material_request_draft(
        self,
        *,
        material_request_type: str = "Purchase",
        schedule_date: str | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        return self.call_method(
            "agent_bridge.api.create_material_request_draft",
            {
                "material_request_type": material_request_type,
                "schedule_date": schedule_date,
                "items": items or [],
            },
        )

    def get_pending_procurement_items(
        self,
        *,
        project: str | None = None,
        warehouses: list[str] | None = None,
        limit: int = 500,
    ) -> ToolResult:
        return self.call_method(
            "agent_bridge.api.get_pending_procurement_items",
            {"project": project, "warehouses": warehouses or [], "limit": limit},
        )

    def create_todo(
        self,
        description: str,
        *,
        allocated_to: str | None = None,
        priority: str = "Medium",
        reference_type: str | None = None,
        reference_name: str | None = None,
        date: str | None = None,
    ) -> ToolResult:
        data: dict[str, Any] = {
            "description": description,
            "priority": priority,
        }
        if allocated_to:
            data["allocated_to"] = allocated_to
        if reference_type:
            data["reference_type"] = reference_type
        if reference_name:
            data["reference_name"] = reference_name
        if date:
            data["date"] = date
        return self.create_document("ToDo", data)

    def setup_item_master(self) -> ToolResult:
        return self.call_method("agent_bridge.api.setup_item_master")

    def prepare_item_from_intent(self, intent: dict[str, Any]) -> ToolResult:
        return self.call_method("agent_bridge.api.prepare_item_from_intent", {"intent": intent})

    def create_item_from_intent(self, intent: dict[str, Any]) -> ToolResult:
        return self.call_method("agent_bridge.api.create_item_from_intent", {"intent": intent})

    def add_comment(
        self,
        reference_doctype: str,
        reference_name: str,
        content: str,
        *,
        comment_email: str = "agent@example.com",
        comment_by: str = "Nexterp Agent",
    ) -> ToolResult:
        return self.call_method(
            "frappe.desk.form.utils.add_comment",
            {
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "content": content,
                "comment_email": comment_email,
                "comment_by": comment_by,
            },
        )

    def get_comments(self, reference_doctype: str, reference_name: str, limit: int = 20) -> ToolResult:
        return self.search_documents(
            "Comment",
            filters={
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
            },
            fields=["name", "comment_type", "content", "comment_by", "creation"],
            limit=limit,
            order_by="creation desc",
        )

    def assign_to(
        self,
        doctype: str,
        name: str,
        assign_to: list[str],
        *,
        description: str | None = None,
        priority: str = "Medium",
        date: str | None = None,
    ) -> ToolResult:
        args: dict[str, Any] = {
            "doctype": doctype,
            "name": name,
            "assign_to": assign_to,
            "priority": priority,
        }
        if description:
            args["description"] = description
        if date:
            args["date"] = date
        return self.call_method("frappe.desk.form.assign_to.add", {"args": args})

    def clear_assignment(self, doctype: str, name: str, assign_to: str) -> ToolResult:
        return self.call_method(
            "frappe.desk.form.assign_to.remove",
            {"doctype": doctype, "name": name, "assign_to": assign_to},
        )

    def attach_file(
        self,
        doctype: str,
        name: str,
        file_path: str,
        *,
        is_private: bool = True,
        fieldname: str | None = None,
    ) -> ToolResult:
        path = Path(file_path)
        if not path.exists():
            return ToolResult(
                ok=False,
                error=f"File not found: {file_path}",
                error_type="not_found",
                user_message="要上传的文件不存在。",
            )
        data = {
            "doctype": doctype,
            "docname": name,
            "is_private": "1" if is_private else "0",
            "folder": "Home",
            "file_name": path.name,
        }
        if fieldname:
            data["fieldname"] = fieldname

        with path.open("rb") as handle:
            try:
                response = self.session.post(
                    self.base_url + "/api/method/upload_file",
                    data=data,
                    files={"file": (path.name, handle)},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                return ToolResult(
                    ok=False,
                    error=str(exc),
                    error_type="network_error",
                    user_message="无法连接 ERPNext，请检查网络或服务状态。",
                )

        payload = _parse_json_response(response)
        if not response.ok:
            error = _extract_error(payload)
            return ToolResult(
                ok=False,
                status_code=response.status_code,
                raw_status_code=response.status_code,
                error=error,
                error_type=classify_error(response.status_code, payload, error),
                user_message=build_user_message(response.status_code, payload, error),
                data=payload,
                debug={"raw_response": payload},
            )
        return ToolResult(
            ok=True,
            status_code=response.status_code,
            raw_status_code=response.status_code,
            data=_extract_data(payload),
        )

    def list_attachments(self, doctype: str, name: str) -> ToolResult:
        return self.search_documents(
            "File",
            filters={"attached_to_doctype": doctype, "attached_to_name": name},
            fields=["name", "file_name", "file_url", "is_private", "creation"],
            limit=100,
            order_by="creation desc",
        )

    def delete_attachment(self, file_name: str) -> ToolResult:
        return self.delete_document("File", file_name)

    def get_stock_balance(
        self,
        item_code: str | None = None,
        *,
        warehouse: str | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if item_code:
            filters["item_code"] = item_code
        if warehouse:
            filters["warehouse"] = warehouse
        return self.search_documents(
            "Bin",
            filters=filters,
            fields=fields
            or [
                "name",
                "item_code",
                "warehouse",
                "actual_qty",
                "projected_qty",
                "reserved_qty",
                "ordered_qty",
                "planned_qty",
                "valuation_rate",
                "stock_value",
            ],
            limit=limit,
            order_by="modified desc",
        )

    def get_item_stock_locations(self, item_code: str, *, include_zero: bool = False, limit: int = 100) -> ToolResult:
        filters: list[list[Any]] = [["item_code", "=", item_code]]
        if not include_zero:
            filters.append(["actual_qty", ">", 0])
        return self.search_documents(
            "Bin",
            filters=filters,
            fields=[
                "name",
                "item_code",
                "warehouse",
                "actual_qty",
                "projected_qty",
                "reserved_qty",
                "valuation_rate",
                "stock_value",
            ],
            limit=limit,
            order_by="actual_qty desc",
        )

    def get_stock_ledger_entries(
        self,
        *,
        item_code: str | None = None,
        warehouse: str | None = None,
        voucher_type: str | None = None,
        voucher_no: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if item_code:
            filters["item_code"] = item_code
        if warehouse:
            filters["warehouse"] = warehouse
        if voucher_type:
            filters["voucher_type"] = voucher_type
        if voucher_no:
            filters["voucher_no"] = voucher_no
        return self.search_documents(
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
                "incoming_rate",
                "valuation_rate",
                "stock_value",
                "stock_value_difference",
                "voucher_type",
                "voucher_no",
                "batch_no",
                "serial_no",
                "is_cancelled",
            ],
            limit=limit,
            order_by="posting_date desc, posting_time desc, creation desc",
        )

    def get_stock_settings(self) -> ToolResult:
        return self.get_document("Stock Settings", "Stock Settings")

    def create_stock_entry_draft(self, data: dict[str, Any]) -> ToolResult:
        doc = {
            "docstatus": 0,
            "stock_entry_type": data.get("stock_entry_type") or data.get("purpose"),
            "purpose": data.get("purpose") or data.get("stock_entry_type"),
            "company": data.get("company"),
            "posting_date": data.get("posting_date"),
            "posting_time": data.get("posting_time"),
            "remarks": data.get("remarks"),
            "items": [_clean_none_values(item) for item in data.get("items", [])],
        }
        return self.create_document("Stock Entry", _clean_none_values(doc))

    def create_stock_reconciliation_draft(self, data: dict[str, Any]) -> ToolResult:
        doc = {
            "docstatus": 0,
            "company": data.get("company"),
            "posting_date": data.get("posting_date"),
            "posting_time": data.get("posting_time"),
            "purpose": data.get("purpose"),
            "expense_account": data.get("expense_account"),
            "cost_center": data.get("cost_center"),
            "remarks": data.get("remarks"),
            "items": [_clean_none_values(item) for item in data.get("items", [])],
        }
        return self.create_document("Stock Reconciliation", _clean_none_values(doc))

    def search_batches(
        self,
        *,
        item_code: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: list[list[Any]] = []
        if item_code:
            filters.append(["item", "=", item_code])
        if query:
            filters.append(["name", "like", f"%{query}%"])
        return self.search_documents(
            "Batch",
            filters=filters,
            fields=["name", "batch_id", "item", "manufacturing_date", "expiry_date", "disabled"],
            limit=limit,
            order_by="creation desc",
        )

    def search_serial_numbers(
        self,
        *,
        item_code: str | None = None,
        warehouse: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: list[list[Any]] = []
        if item_code:
            filters.append(["item_code", "=", item_code])
        if warehouse:
            filters.append(["warehouse", "=", warehouse])
        if status:
            filters.append(["status", "=", status])
        if query:
            filters.append(["name", "like", f"%{query}%"])
        return self.search_documents(
            "Serial No",
            filters=filters,
            fields=["name", "serial_no", "item_code", "warehouse", "status", "batch_no", "purchase_document_no"],
            limit=limit,
            order_by="modified desc",
        )

    def list_warehouses(self, *, company: str | None = None, query: str | None = None, limit: int = 100) -> ToolResult:
        filters: list[list[Any]] = []
        if company:
            filters.append(["company", "=", company])
        if query:
            filters.append(["warehouse_name", "like", f"%{query}%"])
        return self.search_documents(
            "Warehouse",
            filters=filters,
            fields=["name", "warehouse_name", "parent_warehouse", "company", "is_group", "disabled"],
            limit=limit,
            order_by="lft asc",
        )

    def create_warehouse(self, data: dict[str, Any]) -> ToolResult:
        return self.create_document("Warehouse", _clean_none_values(data))

    def update_warehouse(self, name: str, data: dict[str, Any]) -> ToolResult:
        return self.update_document("Warehouse", name, _clean_none_values(data))

    def create_batch(self, data: dict[str, Any]) -> ToolResult:
        return self.create_document("Batch", _clean_none_values(data))

    def update_batch(self, name: str, data: dict[str, Any]) -> ToolResult:
        return self.update_document("Batch", name, _clean_none_values(data))

    def create_serial_no(self, data: dict[str, Any]) -> ToolResult:
        return self.create_document("Serial No", _clean_none_values(data))

    def update_serial_no(self, name: str, data: dict[str, Any]) -> ToolResult:
        return self.update_document("Serial No", name, _clean_none_values(data))

    def list_pick_lists(
        self,
        *,
        purpose: str | None = None,
        status: str | None = None,
        customer: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if purpose:
            filters["purpose"] = purpose
        if status:
            filters["status"] = status
        if customer:
            filters["customer"] = customer
        return self.search_documents(
            "Pick List",
            filters=filters,
            fields=["name", "purpose", "customer", "work_order", "material_request", "sales_order", "status", "docstatus", "modified"],
            limit=limit,
            order_by="modified desc",
        )

    def create_pick_list_draft(self, data: dict[str, Any]) -> ToolResult:
        doc = {
            "docstatus": 0,
            "purpose": data.get("purpose"),
            "customer": data.get("customer"),
            "work_order": data.get("work_order"),
            "material_request": data.get("material_request"),
            "sales_order": data.get("sales_order"),
            "parent_warehouse": data.get("parent_warehouse"),
            "locations": [_clean_none_values(item) for item in data.get("locations", [])],
        }
        return self.create_document("Pick List", _clean_none_values(doc))

    def list_stock_reservations(
        self,
        *,
        item_code: str | None = None,
        warehouse: str | None = None,
        voucher_type: str | None = None,
        voucher_no: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if item_code:
            filters["item_code"] = item_code
        if warehouse:
            filters["warehouse"] = warehouse
        if voucher_type:
            filters["voucher_type"] = voucher_type
        if voucher_no:
            filters["voucher_no"] = voucher_no
        if status:
            filters["status"] = status
        return self.search_documents(
            "Stock Reservation Entry",
            filters=filters,
            fields=[
                "name",
                "item_code",
                "warehouse",
                "voucher_type",
                "voucher_no",
                "voucher_detail_no",
                "reserved_qty",
                "delivered_qty",
                "status",
                "docstatus",
                "modified",
            ],
            limit=limit,
            order_by="modified desc",
        )

    def create_stock_reservation_draft(self, data: dict[str, Any]) -> ToolResult:
        doc = {
            "docstatus": 0,
            "item_code": data.get("item_code"),
            "warehouse": data.get("warehouse"),
            "voucher_type": data.get("voucher_type"),
            "voucher_no": data.get("voucher_no"),
            "voucher_detail_no": data.get("voucher_detail_no"),
            "reserved_qty": data.get("reserved_qty"),
            "company": data.get("company"),
            "stock_uom": data.get("stock_uom"),
            "from_voucher_type": data.get("from_voucher_type"),
        }
        return self.create_document("Stock Reservation Entry", _clean_none_values(doc))

    def preview_stock_valuation(self, items: list[dict[str, Any]]) -> ToolResult:
        return self.call_method("agent_bridge.api.preview_stock_valuation", {"items": items})

    def allocate_stock_shortages(self, items: list[dict[str, Any]]) -> ToolResult:
        return self.call_method("agent_bridge.api.allocate_stock_shortages", {"items": items})

    def list_delivery_notes(
        self,
        *,
        customer: str | None = None,
        status: str | None = None,
        docstatus: int | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if customer:
            filters["customer"] = customer
        if status:
            filters["status"] = status
        if docstatus is not None:
            filters["docstatus"] = docstatus
        return self.search_documents(
            "Delivery Note",
            filters=filters,
            fields=["name", "customer", "customer_name", "posting_date", "status", "docstatus", "per_installed", "modified"],
            limit=limit,
            order_by="modified desc",
        )

    def list_purchase_receipts(
        self,
        *,
        supplier: str | None = None,
        status: str | None = None,
        docstatus: int | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if supplier:
            filters["supplier"] = supplier
        if status:
            filters["status"] = status
        if docstatus is not None:
            filters["docstatus"] = docstatus
        return self.search_documents(
            "Purchase Receipt",
            filters=filters,
            fields=["name", "supplier", "supplier_name", "posting_date", "status", "docstatus", "per_billed", "modified"],
            limit=limit,
            order_by="modified desc",
        )

    def list_item_reorders(
        self,
        *,
        item_code: str | None = None,
        warehouse: str | None = None,
        material_request_type: str | None = None,
        limit: int = 100,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if item_code:
            filters["parent"] = item_code
        if warehouse:
            filters["warehouse"] = warehouse
        if material_request_type:
            filters["material_request_type"] = material_request_type
        return self.search_documents(
            "Item Reorder",
            filters=filters,
            fields=[
                "name",
                "parent",
                "parenttype",
                "warehouse",
                "warehouse_reorder_level",
                "warehouse_reorder_qty",
                "material_request_type",
            ],
            limit=limit,
            order_by="parent asc, warehouse asc",
        )

    def list_quality_inspections(
        self,
        *,
        item_code: str | None = None,
        reference_type: str | None = None,
        reference_name: str | None = None,
        inspection_type: str | None = None,
        status: str | None = None,
        docstatus: int | None = None,
        limit: int = 50,
    ) -> ToolResult:
        filters: dict[str, Any] = {}
        if item_code:
            filters["item_code"] = item_code
        if reference_type:
            filters["reference_type"] = reference_type
        if reference_name:
            filters["reference_name"] = reference_name
        if inspection_type:
            filters["inspection_type"] = inspection_type
        if status:
            filters["status"] = status
        if docstatus is not None:
            filters["docstatus"] = docstatus
        return self.search_documents(
            "Quality Inspection",
            filters=filters,
            fields=[
                "name",
                "inspection_type",
                "reference_type",
                "reference_name",
                "item_code",
                "sample_size",
                "status",
                "docstatus",
                "inspected_by",
                "report_date",
                "modified",
            ],
            limit=limit,
            order_by="modified desc",
        )

    def submit_stock_document(self, doctype: str, name: str) -> ToolResult:
        return self.submit_document(doctype, name)


def normalize_filters(filters: dict[str, Any] | list[Any]) -> list[Any]:
    """Normalize compact dict filters into Frappe's list filter format."""

    if isinstance(filters, list):
        return filters

    normalized = []
    for field, value in filters.items():
        if isinstance(value, list) and len(value) == 2:
            normalized.append([field, value[0], value[1]])
        else:
            normalized.append([field, "=", value])
    return normalized


def _clean_none_values(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _parse_json_response(response: requests.Response) -> Any:
    if not response.text:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def _extract_data(payload: Any) -> Any:
    if isinstance(payload, dict):
        if "data" in payload:
            return payload["data"]
        if "message" in payload:
            return payload["message"]
    return payload


def _extract_error(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("exception", "exc_type", "exc", "_server_messages", "message"):
            value = payload.get(key)
            if value:
                return str(value)
    return str(payload)


def classify_error(status_code: int | None, payload: Any, error: str) -> str:
    text = error.lower()
    payload_text = json.dumps(payload, ensure_ascii=False).lower() if isinstance(payload, (dict, list)) else str(payload).lower()
    combined = f"{text} {payload_text}"

    if status_code in (401, 403) or "permissionerror" in combined or "not permitted" in combined:
        return "permission_error" if status_code == 403 else "auth_error"
    if status_code == 404 or "does not exist" in combined or "not found" in combined:
        return "not_found"
    if "duplicate" in combined or "duplicateentryerror" in combined:
        return "duplicate_error"
    if "linkvalidationerror" in combined or "linkexistserror" in combined or "could not find" in combined:
        return "link_validation_error"
    if "mandatory" in combined or "missing" in combined and "argument" in combined:
        return "missing_argument"
    if "validationerror" in combined or "validation" in combined:
        return "validation_error"
    if status_code and status_code >= 400:
        return "http_error"
    return "unknown_error"


def build_user_message(status_code: int | None, payload: Any, error: str) -> str:
    error_type = classify_error(status_code, payload, error)
    messages = {
        "auth_error": "ERPNext 认证失败，请检查 API Key 和 Secret。",
        "permission_error": "当前 ERPNext 用户没有执行这个操作的权限。",
        "not_found": "ERPNext 中没有找到对应的数据。",
        "validation_error": "ERPNext 校验失败，请检查字段和值是否符合单据要求。",
        "duplicate_error": "ERPNext 中已经存在重复数据。",
        "missing_argument": "工具调用缺少必要参数。",
        "link_validation_error": "单据关联的数据不存在、不正确，或仍被其他业务记录引用。",
        "http_error": "ERPNext 请求失败。",
        "network_error": "无法连接 ERPNext，请检查网络或服务状态。",
        "unknown_error": "ERPNext 返回了未分类错误。",
    }
    return messages.get(error_type, "ERPNext 请求失败。")
