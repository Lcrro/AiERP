from __future__ import annotations

from .common import _object_schema


PROJECT_MATERIAL_ISSUE_ITEM_SCHEMA = {
    "type": "object",
    "required": ["qty"],
    "properties": {
        "item_code": {"type": "string"},
        "item_query": {"type": "string"},
        "selected_item_code": {"type": "string"},
        "selection_confirmed": {"type": "boolean"},
        "qty": {"type": "number", "exclusiveMinimum": 0},
        "uom": {"type": "string"},
        "basic_rate": {"type": "number", "minimum": 0},
        "expense_account": {"type": "string"},
        "cost_center": {"type": "string"},
        "description": {"type": "string"},
        "task": {"type": "string"},
    },
}


PROJECTS_TOOL_SCHEMAS = [
    {
        "name": "erpnext.projects.get_project_cost_context",
        "description": "Read project cost context from Project, Task, Stock Entry, and Purchase Receipt records.",
        "parameters": _object_schema(
            ["project"],
            {
                "project": {"type": "string"},
                "company": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "include_tasks": {"type": "boolean"},
                "include_stock_entries": {"type": "boolean"},
                "include_purchase_receipts": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.projects.get_material_issue_context",
        "description": "Preview project material issue demand against source warehouse availability before creating a Stock Entry draft.",
        "parameters": _object_schema(
            ["project", "source_warehouse", "items"],
            {
                "project": {"type": "string"},
                "source_warehouse": {"type": "string"},
                "items": {"type": "array", "items": PROJECT_MATERIAL_ISSUE_ITEM_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.projects.create_material_issue_draft",
        "description": "Create a project material issue Stock Entry draft with project and cost-center context. Does not submit stock movement.",
        "parameters": _object_schema(
            ["project", "source_warehouse", "items"],
            {
                "project": {"type": "string"},
                "source_warehouse": {"type": "string"},
                "company": {"type": "string"},
                "posting_date": {"type": "string"},
                "posting_time": {"type": "string"},
                "cost_center": {"type": "string"},
                "expense_account": {"type": "string"},
                "remarks": {"type": "string"},
                "require_available_stock": {"type": "boolean"},
                "items": {"type": "array", "items": PROJECT_MATERIAL_ISSUE_ITEM_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.projects.verify_material_issue_cost_impact",
        "description": "Verify a submitted project Material Issue Stock Entry against project/cost-center item rows and stock ledger value impact. Read-only L0.",
        "parameters": _object_schema(
            ["stock_entry"],
            {
                "stock_entry": {"type": "string"},
                "project": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        ),
    },
]
