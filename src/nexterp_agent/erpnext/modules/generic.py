from __future__ import annotations

import os
from typing import Any

from nexterp_agent.item_master import MaterialSearch, PostgresCatalogSearchClient

from ..schemas import ToolResult
from .common import *

class GenericToolsMixin:
    def _get_logged_user(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_logged_user()

    def _search_documents(self, args: dict[str, Any]) -> ToolResult:
        return self.client.search_documents(
            args["doctype"],
            filters=args.get("filters"),
            fields=args.get("fields"),
            limit=args.get("limit", 20),
            offset=args.get("offset", 0),
            order_by=args.get("order_by"),
        )

    def _search_items(self, args: dict[str, Any]) -> ToolResult:
        search = MaterialSearch(self.client)
        return ToolResult(
            ok=True,
            data=search.search_items(
                args["query"],
                specs=args.get("specs"),
                item_group=args.get("item_group"),
                enabled_only=args.get("enabled_only", True),
                limit=args.get("limit", 10),
            ),
        )

    def _count_documents(self, args: dict[str, Any]) -> ToolResult:
        return self.client.count_documents(args["doctype"], filters=args.get("filters"))

    def _get_document(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_document(args["doctype"], args["name"])

    def _create_document(self, args: dict[str, Any]) -> ToolResult:
        data = args.get("data") if isinstance(args.get("data"), dict) else {}
        guard = _require_accounting_write_confirmation(
            "generic_create_document",
            args["doctype"],
            data.get("name"),
            args.get("confirmation"),
        )
        if guard:
            return guard
        return self.client.create_document(args["doctype"], args["data"])

    def _update_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_accounting_write_confirmation(
            "generic_update_document",
            args["doctype"],
            args["name"],
            args.get("confirmation"),
        )
        if guard:
            return guard
        return self.client.update_document(args["doctype"], args["name"], args["data"])

    def _delete_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_accounting_write_confirmation(
            "generic_delete_document",
            args["doctype"],
            args["name"],
            args.get("confirmation"),
        )
        if guard:
            return guard
        return self.client.delete_document(args["doctype"], args["name"])

    def _document_exists(self, args: dict[str, Any]) -> ToolResult:
        return self.client.document_exists(args["doctype"], args["name"])

    def _resolve_link(self, args: dict[str, Any]) -> ToolResult:
        return self.client.resolve_link(
            args["doctype"],
            args["query"],
            search_field=args.get("search_field", "name"),
            limit=args.get("limit", 10),
        )

    def _validate_fields(self, args: dict[str, Any]) -> ToolResult:
        return self.client.validate_fields(args["doctype"], args["fields"])

    def _get_doctype_schema(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_doctype_schema(args["doctype"])

    def _call_method(self, args: dict[str, Any]) -> ToolResult:
        method_args = args.get("args") if isinstance(args.get("args"), dict) else {}
        guarded_doctype = _call_method_doctype(args["method"], method_args)
        if args["method"] in ACCOUNTING_MUTATING_METHODS:
            guard = _require_accounting_write_confirmation(
                args["method"],
                guarded_doctype,
                _call_method_name(method_args),
                args.get("confirmation"),
            )
            if guard:
                return guard
        if args["method"] in {"agent_bridge.api.submit_document", "agent_bridge.api.cancel_document"}:
            guard = _require_financial_confirmation(guarded_doctype, args.get("confirmation"))
            if guard:
                return guard
            stock_guard = _require_stock_confirmation(guarded_doctype, method_args.get("name"), args.get("confirmation"))
            if stock_guard:
                return stock_guard
            asset_guard = _require_asset_confirmation(guarded_doctype, method_args.get("name"), args.get("confirmation"))
            if asset_guard:
                return asset_guard
        return self.client.call_method(
            args["method"],
            args.get("args", {}),
            http_method=args.get("http_method", "POST"),
        )

    def _submit_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_financial_confirmation(args["doctype"], args.get("confirmation"))
        if guard:
            return guard
        stock_guard = _require_stock_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if stock_guard:
            return stock_guard
        asset_guard = _require_asset_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if asset_guard:
            return asset_guard
        return self.client.submit_document(args["doctype"], args["name"])

    def _cancel_document(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_financial_confirmation(args["doctype"], args.get("confirmation"))
        if guard:
            return guard
        stock_guard = _require_stock_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if stock_guard:
            return stock_guard
        asset_guard = _require_asset_confirmation(args["doctype"], args["name"], args.get("confirmation"))
        if asset_guard:
            return asset_guard
        return self.client.cancel_document(args["doctype"], args["name"])

    def _amend_document(self, args: dict[str, Any]) -> ToolResult:
        return self.client.amend_document(args["doctype"], args["name"])

    def _get_workflow_actions(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_workflow_actions(args["doctype"], args["name"])

    def _apply_workflow(self, args: dict[str, Any]) -> ToolResult:
        return self.client.apply_workflow(args["doctype"], args["name"], args["action"])

    def _run_report(self, args: dict[str, Any]) -> ToolResult:
        return self.client.run_report(
            args["report_name"],
            filters=args.get("filters"),
            ignore_prepared_report=args.get("ignore_prepared_report", True),
        )

    def _setup_item_master(self, args: dict[str, Any]) -> ToolResult:
        return self.client.setup_item_master()

    def _prepare_item_from_intent(self, args: dict[str, Any]) -> ToolResult:
        return self.client.prepare_item_from_intent(args["intent"])

    def _create_item_from_intent(self, args: dict[str, Any]) -> ToolResult:
        return self.client.create_item_from_intent(args["intent"])

    def _create_todo(self, args: dict[str, Any]) -> ToolResult:
        return self.client.create_todo(
            args["description"],
            allocated_to=args.get("allocated_to"),
            priority=args.get("priority", "Medium"),
            reference_type=args.get("reference_type"),
            reference_name=args.get("reference_name"),
            date=args.get("date"),
        )

    def _add_comment(self, args: dict[str, Any]) -> ToolResult:
        return self.client.add_comment(
            args["reference_doctype"],
            args["reference_name"],
            args["content"],
            comment_email=args.get("comment_email", "agent@example.com"),
            comment_by=args.get("comment_by", "Nexterp Agent"),
        )

    def _get_comments(self, args: dict[str, Any]) -> ToolResult:
        return self.client.get_comments(
            args["reference_doctype"],
            args["reference_name"],
            limit=args.get("limit", 20),
        )

    def _assign_to(self, args: dict[str, Any]) -> ToolResult:
        return self.client.assign_to(
            args["doctype"],
            args["name"],
            args["assign_to"],
            description=args.get("description"),
            priority=args.get("priority", "Medium"),
            date=args.get("date"),
        )

    def _clear_assignment(self, args: dict[str, Any]) -> ToolResult:
        return self.client.clear_assignment(args["doctype"], args["name"], args["assign_to"])

    def _attach_file(self, args: dict[str, Any]) -> ToolResult:
        return self.client.attach_file(
            args["doctype"],
            args["name"],
            args["file_path"],
            is_private=args.get("is_private", True),
            fieldname=args.get("fieldname"),
        )

    def _list_attachments(self, args: dict[str, Any]) -> ToolResult:
        return self.client.list_attachments(args["doctype"], args["name"])

    def _delete_attachment(self, args: dict[str, Any]) -> ToolResult:
        return self.client.delete_attachment(args["file_name"])
