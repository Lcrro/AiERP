from __future__ import annotations

from typing import Any

from ..schemas import ToolResult
from .common import *


class ProjectsToolsMixin:
    def _projects_get_project_exceptions(self, args: dict[str, Any]) -> ToolResult:
        project_name = args["project"]
        as_of = args.get("as_of_date")
        project_result = self.client.get_document("Project", project_name)
        if not project_result.ok:
            return project_result
        project = project_result.data if isinstance(project_result.data, dict) else {}
        task_result = self.client.search_documents(
            "Task",
            filters={"project": project_name},
            fields=["name", "subject", "status", "priority", "progress", "exp_end_date", "modified"],
            limit=args.get("limit", 100),
            order_by="exp_end_date asc, priority desc",
        )
        if not task_result.ok:
            return task_result
        tasks = [row for row in (task_result.data if isinstance(task_result.data, list) else []) if isinstance(row, dict)]
        active_statuses = {"Open", "Working", "Pending Review", "Overdue"}
        overdue = [
            row for row in tasks
            if row.get("status") in active_statuses and row.get("exp_end_date") and as_of and str(row["exp_end_date"]) < str(as_of)
        ]
        due_without_progress = [
            row for row in tasks
            if row.get("status") in active_statuses and row.get("exp_end_date") and not row.get("progress")
        ]
        project_delayed = bool(
            as_of
            and project.get("expected_end_date")
            and str(project["expected_end_date"]) < str(as_of)
            and project.get("status") not in {"Completed", "Cancelled"}
        )
        signals = []
        if project_delayed:
            signals.append({"type": "project_end_date_overdue", "expected_end_date": project.get("expected_end_date")})
        if overdue:
            signals.append({"type": "overdue_tasks", "count": len(overdue)})
        if due_without_progress:
            signals.append({"type": "tasks_without_progress", "count": len(due_without_progress)})
        return ToolResult(ok=True, data={
            "doctype": "Project",
            "name": project.get("name") or project_name,
            "status": "Review Required" if signals else "No Exceptions",
            "as_of_date": as_of,
            "project": _clean_mapping({
                "project_name": project.get("project_name"),
                "project_status": project.get("status"),
                "expected_end_date": project.get("expected_end_date"),
                "percent_complete": project.get("percent_complete"),
                "total_costing_amount": project.get("total_costing_amount"),
                "total_billing_amount": project.get("total_billing_amount"),
            }),
            "signals": signals,
            "overdue_tasks": overdue,
            "tasks_without_progress": due_without_progress,
            "risk": {"level": "L0", "writes_document": False},
        })

    def _projects_create_task(self, args: dict[str, Any]) -> ToolResult:
        project_result = self.client.get_document("Project", args["project"])
        if not project_result.ok:
            return project_result
        if args.get("exp_start_date") and args.get("exp_end_date") and args["exp_start_date"] > args["exp_end_date"]:
            return ToolResult(ok=False, error_type="validation_error", error="Task start date is after end date.", user_message="任务开始日期不能晚于结束日期。")
        data = _without_empty({
            "doctype": "Task",
            "project": args["project"],
            "subject": args["subject"],
            "description": args.get("description"),
            "priority": args.get("priority") or "Medium",
            "status": "Open",
            "exp_start_date": args.get("exp_start_date"),
            "exp_end_date": args.get("exp_end_date"),
        })
        return _module_doc_result(
            self.client.create_document("Task", data),
            "Task",
            "L3",
            f"Created task under project {args['project']}.",
            ["review_task", "assign_owner"],
            requires_confirmation_for_submit=False,
        )

    def _projects_update_task(self, args: dict[str, Any]) -> ToolResult:
        task_result = self.client.get_document("Task", args["task"])
        if not task_result.ok:
            return task_result
        task = task_result.data if isinstance(task_result.data, dict) else {}
        allowed = {"status", "progress", "priority", "exp_start_date", "exp_end_date", "description"}
        changes = _without_empty({field: args.get(field) for field in allowed})
        if not changes:
            return ToolResult(ok=False, error_type="missing_argument", error="No task changes supplied.", user_message="请至少说明一项要修改的任务内容。")
        start = changes.get("exp_start_date") or task.get("exp_start_date")
        end = changes.get("exp_end_date") or task.get("exp_end_date")
        if start and end and str(start) > str(end):
            return ToolResult(ok=False, error_type="validation_error", error="Task start date is after end date.", user_message="任务开始日期不能晚于结束日期。")
        result = self.client.update_document("Task", args["task"], changes)
        return _module_doc_result(result, "Task", "L3", f"Updated task {args['task']}.", ["review_task"], requires_confirmation_for_submit=False)

    def _projects_get_project_cost_context(self, args: dict[str, Any]) -> ToolResult:
        project_name = args["project"]
        project_result = self.client.get_document("Project", project_name)
        if not project_result.ok:
            return project_result
        project = project_result.data if isinstance(project_result.data, dict) else {}
        limit = args.get("limit", 20)

        tasks: list[dict[str, Any]] = []
        stock_entries: list[dict[str, Any]] = []
        purchase_receipts: list[dict[str, Any]] = []

        if args.get("include_tasks", True):
            task_result = self.client.search_documents(
                "Task",
                filters={"project": project_name},
                fields=[
                    "name",
                    "subject",
                    "status",
                    "priority",
                    "progress",
                    "exp_start_date",
                    "exp_end_date",
                    "total_costing_amount",
                    "total_billing_amount",
                    "modified",
                ],
                limit=limit,
                order_by="modified desc",
            )
            if not task_result.ok:
                return task_result
            tasks = task_result.data if isinstance(task_result.data, list) else []

        if args.get("include_stock_entries", True):
            stock_result = self.client.search_documents(
                "Stock Entry",
                filters=_project_document_filters(args, project_name, "posting_date"),
                fields=[
                    "name",
                    "stock_entry_type",
                    "purpose",
                    "posting_date",
                    "docstatus",
                    "company",
                    "project",
                    "modified",
                ],
                limit=limit,
                order_by="posting_date desc, modified desc",
            )
            if not stock_result.ok:
                return stock_result
            stock_entries = stock_result.data if isinstance(stock_result.data, list) else []

        if args.get("include_purchase_receipts", True):
            receipt_result = self.client.search_documents(
                "Purchase Receipt",
                filters=_project_document_filters(args, project_name, "posting_date"),
                fields=[
                    "name",
                    "supplier",
                    "posting_date",
                    "docstatus",
                    "company",
                    "project",
                    "cost_center",
                    "net_total",
                    "grand_total",
                    "modified",
                ],
                limit=limit,
                order_by="posting_date desc, modified desc",
            )
            if not receipt_result.ok:
                return receipt_result
            purchase_receipts = receipt_result.data if isinstance(receipt_result.data, list) else []

        data = {
            "doctype": "Project",
            "name": project.get("name") or project_name,
            "docstatus": project.get("docstatus"),
            "status": "Project Cost Context Ready",
            "summary": (
                f"Prepared project cost context for {project_name}: "
                f"{len(tasks)} task(s), {len(stock_entries)} stock entry row(s), "
                f"{len(purchase_receipts)} purchase receipt row(s)."
            ),
            "project": _clean_mapping(
                {
                    "project_name": project.get("project_name"),
                    "status": project.get("status"),
                    "company": project.get("company") or args.get("company"),
                    "cost_center": project.get("cost_center"),
                    "expected_start_date": project.get("expected_start_date"),
                    "expected_end_date": project.get("expected_end_date"),
                    "percent_complete": project.get("percent_complete"),
                    "total_costing_amount": project.get("total_costing_amount"),
                    "total_billing_amount": project.get("total_billing_amount"),
                    "gross_margin": project.get("gross_margin"),
                    "per_gross_margin": project.get("per_gross_margin"),
                }
            ),
            "tasks": tasks,
            "stock_entries": stock_entries,
            "purchase_receipts": purchase_receipts,
            "next_actions": ["review_project_cost_context", "preview_material_issue"],
            "risk": {"level": "L0", "writes_document": False},
        }
        return ToolResult(
            ok=True,
            status_code=project_result.status_code,
            raw_status_code=project_result.raw_status_code,
            data=data,
            debug={"raw_project": project},
        )

    def _projects_get_material_issue_context(self, args: dict[str, Any]) -> ToolResult:
        project_name = args["project"]
        source_warehouse = args["source_warehouse"]
        project_result = self.client.get_document("Project", project_name)
        if not project_result.ok:
            return project_result
        project = project_result.data if isinstance(project_result.data, dict) else {}

        rows: list[dict[str, Any]] = []
        shortages: list[dict[str, Any]] = []
        balance_debug: list[dict[str, Any]] = []
        for item in args["items"]:
            normalized = self._normalize_project_material_issue_item(item, args, project)
            if not normalized.get("item_code"):
                return _item_resolution_error("项目领料预览中存在无法解析 item_code 的行。")

            balance_result = self.client.get_stock_balance(
                normalized["item_code"],
                warehouse=source_warehouse,
                limit=1,
            )
            if not balance_result.ok:
                return balance_result
            balances = balance_result.data if isinstance(balance_result.data, list) else []
            available_qty = _available_stock_qty(balances)
            requested_qty = _float_or_none(normalized.get("qty")) or 0.0
            shortage_qty = max(requested_qty - available_qty, 0.0)
            row = _clean_mapping(
                {
                    "item_code": normalized.get("item_code"),
                    "requested_qty": requested_qty,
                    "available_qty": available_qty,
                    "shortage_qty": shortage_qty,
                    "source_warehouse": source_warehouse,
                    "uom": normalized.get("uom"),
                    "basic_rate": normalized.get("basic_rate"),
                    "expense_account": normalized.get("expense_account"),
                    "cost_center": normalized.get("cost_center"),
                    "description": normalized.get("description"),
                    "task": normalized.get("task"),
                    "can_issue": shortage_qty <= 0,
                }
            )
            rows.append(row)
            if shortage_qty > 0:
                shortages.append(row)
            balance_debug.append({"item_code": normalized.get("item_code"), "raw_balance": balances})

        status = "Ready" if not shortages else "Has Shortage"
        data = {
            "doctype": "Stock Entry",
            "name": None,
            "docstatus": None,
            "status": status,
            "summary": f"Prepared project material issue preview for {project_name}: {len(shortages)} shortage row(s).",
            "project": _clean_mapping(
                {
                    "name": project.get("name") or project_name,
                    "project_name": project.get("project_name"),
                    "company": project.get("company") or args.get("company"),
                    "cost_center": project.get("cost_center"),
                }
            ),
            "source_warehouse": source_warehouse,
            "items": rows,
            "shortages": shortages,
            "next_actions": ["create_material_issue_draft"] if not shortages else ["review_shortages", "transfer_or_purchase_material"],
            "risk": {"level": "L1", "writes_document": False},
        }
        return ToolResult(
            ok=True,
            status_code=project_result.status_code,
            raw_status_code=project_result.raw_status_code,
            data=data,
            debug={"raw_project": project, "raw_balances": balance_debug},
        )

    def _projects_create_material_issue_draft(self, args: dict[str, Any]) -> ToolResult:
        context = self._projects_get_material_issue_context(args)
        if not context.ok:
            return context
        context_data = context.data if isinstance(context.data, dict) else {}
        shortages = context_data.get("shortages") or []
        if args.get("require_available_stock", True) and shortages:
            return ToolResult(
                ok=False,
                error="Insufficient stock for project material issue draft.",
                error_type="insufficient_stock",
                user_message="项目领料存在缺料，默认不会创建库存出库草稿。请先调拨、采购，或明确允许负库存草稿。",
                data={
                    "doctype": "Stock Entry",
                    "status": "Blocked By Shortage",
                    "summary": f"Blocked material issue draft because {len(shortages)} row(s) are short.",
                    "shortages": shortages,
                    "next_actions": ["review_shortages", "transfer_or_purchase_material", "retry_with_available_stock"],
                    "risk": {"level": "L1", "requires_confirmation_for_submit": False},
                },
                debug=context.debug,
            )

        project = context.debug.get("raw_project") if isinstance(context.debug, dict) else {}
        project = project if isinstance(project, dict) else {}
        cost_center = args.get("cost_center") or project.get("cost_center")
        expense_account = args.get("expense_account")
        source_warehouse = args["source_warehouse"]
        items = [
            _project_stock_entry_item(row, source_warehouse, args["project"], cost_center, expense_account)
            for row in context_data.get("items", [])
        ]
        data = _without_empty(
            {
                "stock_entry_type": "Material Issue",
                "purpose": "Material Issue",
                "company": args.get("company") or project.get("company"),
                "posting_date": args.get("posting_date"),
                "posting_time": args.get("posting_time"),
                "remarks": args.get("remarks") or f"Project material issue for {args['project']}",
                "items": items,
            }
        )
        result = self.client.create_stock_entry_draft(data)
        wrapped = _stock_draft_result(
            result,
            doctype="Stock Entry",
            summary=f"Created project material issue draft for {args['project']} with {len(items)} item row(s).",
        )
        if wrapped.ok and isinstance(wrapped.data, dict):
            wrapped.data["project"] = args["project"]
            wrapped.data["source_warehouse"] = source_warehouse
        if wrapped.ok and isinstance(wrapped.debug, dict):
            wrapped.debug["project_material_issue_context"] = context_data
        return wrapped

    def _projects_verify_material_issue_cost_impact(self, args: dict[str, Any]) -> ToolResult:
        stock_entry_name = args["stock_entry"]
        document = self.client.get_document("Stock Entry", stock_entry_name)
        if not document.ok:
            return document
        doc = document.data if isinstance(document.data, dict) else {}
        ledger = self.client.get_stock_ledger_entries(
            voucher_type="Stock Entry",
            voucher_no=stock_entry_name,
            limit=args.get("limit", 200),
        )
        if not ledger.ok:
            return ledger

        item_rows = _project_material_issue_rows(doc, project=args.get("project"))
        ledger_rows = [row for row in (ledger.data if isinstance(ledger.data, list) else []) if isinstance(row, dict)]
        totals = _project_material_issue_cost_totals(item_rows, ledger_rows)
        warnings = _project_material_issue_cost_warnings(doc, item_rows, ledger_rows, args.get("project"))
        status = "Verified" if doc.get("docstatus") == 1 and not warnings else "Review Required"
        project_names = sorted({row.get("project") for row in item_rows if row.get("project")})
        return ToolResult(
            ok=True,
            status_code=document.status_code,
            raw_status_code=document.raw_status_code,
            data={
                "doctype": "Stock Entry",
                "name": stock_entry_name,
                "docstatus": doc.get("docstatus"),
                "status": status,
                "summary": (
                    f"Verified project material issue cost impact for Stock Entry {stock_entry_name}: "
                    f"{len(item_rows)} project item row(s), {len(ledger_rows)} ledger row(s)."
                ),
                "stock_entry": _clean_mapping(
                    {
                        "stock_entry_type": doc.get("stock_entry_type"),
                        "purpose": doc.get("purpose"),
                        "company": doc.get("company"),
                        "posting_date": doc.get("posting_date"),
                        "project": doc.get("project"),
                    }
                ),
                "projects": project_names,
                "totals": totals,
                "items": item_rows,
                "ledger_entries": ledger_rows,
                "warnings": warnings,
                "next_actions": ["review_project_material_cost"] if warnings else ["review_project_cost_context", "include_in_manager_summary"],
                "risk": {"level": "L0", "writes_document": False, "moves_stock": False},
            },
            debug={"raw_stock_entry": doc, "raw_stock_ledger_entries": ledger_rows},
        )

    def _normalize_project_material_issue_item(self, item: dict[str, Any], args: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
        row = dict(item)
        if row.get("selected_item_code") and not row.get("selection_confirmed"):
            row.pop("item_code", None)
            return row
        if not row.get("item_code"):
            row["item_code"] = self._stock_item_code_from_args(row)
        row["cost_center"] = row.get("cost_center") or args.get("cost_center") or project.get("cost_center")
        row["expense_account"] = row.get("expense_account") or args.get("expense_account")
        allowed_fields = {
            "item_code",
            "qty",
            "uom",
            "basic_rate",
            "expense_account",
            "cost_center",
            "description",
            "task",
        }
        return _without_empty({field: row.get(field) for field in allowed_fields})


def _project_document_filters(args: dict[str, Any], project: str, date_field: str) -> dict[str, Any]:
    filters: dict[str, Any] = {"project": project}
    if args.get("company"):
        filters["company"] = args["company"]
    if args.get("from_date") and args.get("to_date"):
        filters[date_field] = ["between", [args["from_date"], args["to_date"]]]
    elif args.get("from_date"):
        filters[date_field] = [">=", args["from_date"]]
    elif args.get("to_date"):
        filters[date_field] = ["<=", args["to_date"]]
    return filters


def _available_stock_qty(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        total += _float_or_none(row.get("actual_qty")) or 0.0
    return total


def _project_stock_entry_item(
    row: dict[str, Any],
    source_warehouse: str,
    project: str,
    cost_center: str | None,
    expense_account: str | None,
) -> dict[str, Any]:
    return _without_empty(
        {
            "item_code": row.get("item_code"),
            "s_warehouse": source_warehouse,
            "qty": row.get("requested_qty"),
            "uom": row.get("uom"),
            "basic_rate": row.get("basic_rate"),
            "expense_account": row.get("expense_account") or expense_account,
            "cost_center": row.get("cost_center") or cost_center,
            "project": project,
            "description": _project_issue_description(row),
        }
    )


def _project_issue_description(row: dict[str, Any]) -> str | None:
    description = row.get("description")
    task = row.get("task")
    if description and task:
        return f"{description} (Task: {task})"
    if task:
        return f"Project material issue for task {task}"
    return description


def _project_material_issue_rows(doc: dict[str, Any], *, project: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for row in doc.get("items") or []:
        if not isinstance(row, dict):
            continue
        row_project = row.get("project") or doc.get("project")
        if project and row_project != project:
            continue
        qty = _float_or_none(row.get("qty")) or 0.0
        amount = _first_float(row, ("basic_amount", "amount")) or 0.0
        if amount == 0.0:
            amount = qty * (_first_float(row, ("basic_rate", "valuation_rate", "incoming_rate")) or 0.0)
        rows.append(
            _clean_mapping(
                {
                    "name": row.get("name"),
                    "item_code": row.get("item_code"),
                    "item_name": row.get("item_name"),
                    "qty": round(qty, 6),
                    "uom": row.get("uom") or row.get("stock_uom"),
                    "source_warehouse": row.get("s_warehouse"),
                    "target_warehouse": row.get("t_warehouse"),
                    "project": row_project,
                    "cost_center": row.get("cost_center"),
                    "expense_account": row.get("expense_account"),
                    "basic_rate": _first_float(row, ("basic_rate", "valuation_rate", "incoming_rate")),
                    "basic_amount": round(amount, 2),
                }
            )
        )
    return rows


def _project_material_issue_cost_totals(item_rows: list[dict[str, Any]], ledger_rows: list[dict[str, Any]]) -> dict[str, Any]:
    item_qty = sum(_float_or_none(row.get("qty")) or 0.0 for row in item_rows)
    item_amount = sum(_first_float(row, ("basic_amount", "amount")) or 0.0 for row in item_rows)
    ledger_out_qty = abs(sum(min(_float_or_none(row.get("actual_qty")) or 0.0, 0.0) for row in ledger_rows if isinstance(row, dict)))
    ledger_value_difference = sum(_first_float(row, ("stock_value_difference", "stock_value")) or 0.0 for row in ledger_rows if isinstance(row, dict))
    return {
        "item_issue_qty": round(item_qty, 6),
        "item_issue_amount": round(item_amount, 2),
        "ledger_out_qty": round(ledger_out_qty, 6),
        "ledger_value_difference": round(ledger_value_difference, 2),
    }


def _project_material_issue_cost_warnings(
    doc: dict[str, Any],
    item_rows: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
    project: str | None,
) -> list[dict[str, Any]]:
    warnings = []
    purpose = doc.get("purpose") or doc.get("stock_entry_type")
    if purpose != "Material Issue":
        warnings.append({"type": "not_material_issue", "message": "Stock Entry is not a Material Issue."})
    if doc.get("docstatus") != 1:
        warnings.append({"type": "not_submitted", "message": "Stock Entry is not submitted, so project cost and stock ledger impact may not be final."})
    if project and not item_rows:
        warnings.append({"type": "project_not_found_on_items", "message": "No Stock Entry item rows matched the requested project."})
    if item_rows and any(not row.get("project") for row in item_rows):
        warnings.append({"type": "missing_project_on_item", "message": "Some item rows do not carry project context."})
    if doc.get("docstatus") == 1 and not ledger_rows:
        warnings.append({"type": "no_stock_ledger_entries", "message": "Submitted Stock Entry has no matching Stock Ledger Entry rows."})
    return warnings
