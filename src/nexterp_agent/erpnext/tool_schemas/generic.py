from __future__ import annotations

from .common import (
    BUYING_ITEM_LINE_SCHEMA,
    CONFIRMATION_SCHEMA,
    PICK_LIST_LOCATION_SCHEMA,
    STOCK_ENTRY_ITEM_SCHEMA,
    STOCK_PREVIEW_ITEM_SCHEMA,
    STOCK_RECONCILIATION_ITEM_SCHEMA,
    _object_schema,
)

GENERIC_CORE_TOOL_SCHEMAS = [
    {
        "name": "erpnext.get_logged_user",
        "description": "Return the ERPNext user for the current API session.",
        "parameters": _object_schema([], {}),
    },
    {
        "name": "erpnext.search_documents",
        "description": "Search ERPNext documents of a DocType with filters, selected fields, pagination, and ordering.",
        "parameters": _object_schema(
            ["doctype"],
            {
                "doctype": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.search_items",
        "description": "Search standardized ERPNext Item master data by code, name, alias/raw name, specs, and item group. Returns candidates with scores, reasons, status, and clarification questions.",
        "parameters": _object_schema(
            ["query"],
            {
                "query": {"type": "string"},
                "specs": {"type": "object"},
                "item_group": {"type": "string"},
                "enabled_only": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        ),
    },
    {
        "name": "erpnext.count_documents",
        "description": "Count ERPNext documents of a DocType matching optional filters.",
        "parameters": _object_schema(["doctype"], {"doctype": {"type": "string"}, "filters": {"type": ["object", "array"]}}),
    },
    {
        "name": "erpnext.get_document",
        "description": "Get one ERPNext document by DocType and document name.",
        "parameters": _object_schema(["doctype", "name"], {"doctype": {"type": "string"}, "name": {"type": "string"}}),
    },
    {
        "name": "erpnext.create_document",
        "description": "Create a new ERPNext document.",
        "parameters": _object_schema(["doctype", "data"], {"doctype": {"type": "string"}, "data": {"type": "object"}}),
    },
    {
        "name": "erpnext.update_document",
        "description": "Update an existing ERPNext document.",
        "parameters": _object_schema(["doctype", "name", "data"], {"doctype": {"type": "string"}, "name": {"type": "string"}, "data": {"type": "object"}}),
    },
    {
        "name": "erpnext.delete_document",
        "description": "Delete an ERPNext document.",
        "parameters": _object_schema(["doctype", "name"], {"doctype": {"type": "string"}, "name": {"type": "string"}}),
    },
    {
        "name": "erpnext.document_exists",
        "description": "Check whether an ERPNext document exists.",
        "parameters": _object_schema(["doctype", "name"], {"doctype": {"type": "string"}, "name": {"type": "string"}}),
    },
    {
        "name": "erpnext.resolve_link",
        "description": "Find candidate documents for a Link field value.",
        "parameters": _object_schema(
            ["doctype", "query"],
            {
                "doctype": {"type": "string"},
                "query": {"type": "string"},
                "search_field": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        ),
    },
    {
        "name": "erpnext.validate_fields",
        "description": "Validate that field names exist on a DocType before using them in a ToolCall.",
        "parameters": _object_schema(
            ["doctype", "fields"],
            {
                "doctype": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
        ),
    },
    {
        "name": "erpnext.get_doctype_schema",
        "description": "Read ERPNext DocType metadata and field schema.",
        "parameters": _object_schema(["doctype"], {"doctype": {"type": "string"}}),
    },
    {
        "name": "erpnext.submit_document",
        "description": "Submit a submittable ERPNext document through normal server-side rules.",
        "parameters": _object_schema(
            ["doctype", "name"],
            {
                "doctype": {"type": "string"},
                "name": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        ),
    },
    {
        "name": "erpnext.cancel_document",
        "description": "Cancel a submitted ERPNext document through normal server-side rules.",
        "parameters": _object_schema(
            ["doctype", "name"],
            {
                "doctype": {"type": "string"},
                "name": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        ),
    },
    {
        "name": "erpnext.amend_document",
        "description": "Create an amended draft from a cancelled ERPNext document.",
        "parameters": _object_schema(["doctype", "name"], {"doctype": {"type": "string"}, "name": {"type": "string"}}),
    },
    {
        "name": "erpnext.get_workflow_actions",
        "description": "List available workflow actions for an ERPNext document.",
        "parameters": _object_schema(["doctype", "name"], {"doctype": {"type": "string"}, "name": {"type": "string"}}),
    },
    {
        "name": "erpnext.apply_workflow",
        "description": "Apply a workflow action to an ERPNext document.",
        "parameters": _object_schema(["doctype", "name", "action"], {"doctype": {"type": "string"}, "name": {"type": "string"}, "action": {"type": "string"}}),
    },
    {
        "name": "erpnext.run_report",
        "description": "Run an ERPNext query/script report and return normalized report data.",
        "parameters": _object_schema(["report_name"], {"report_name": {"type": "string"}, "filters": {"type": "object"}, "ignore_prepared_report": {"type": "boolean"}}),
    },
]

GENERIC_AGENT_TOOL_SCHEMAS = [
    {
        "name": "erpnext.setup_item_master",
        "description": "Create the custom ERPNext Item fields required by the material master v0.1 rules. Repeatable.",
        "parameters": _object_schema([], {}),
    },
    {
        "name": "erpnext.prepare_item_from_intent",
        "description": "Validate and normalize a material intent without creating an ERPNext Item.",
        "parameters": _object_schema(["intent"], {"intent": {"type": "object"}}),
    },
    {
        "name": "erpnext.create_item_from_intent",
        "description": "Create an ERPNext Item from a validated material intent using material master rules.",
        "parameters": _object_schema(["intent"], {"intent": {"type": "object"}}),
    },
    {
        "name": "erpnext.create_todo",
        "description": "Create a ToDo follow-up task.",
        "parameters": _object_schema(
            ["description"],
            {
                "description": {"type": "string"},
                "allocated_to": {"type": "string"},
                "priority": {"type": "string"},
                "reference_type": {"type": "string"},
                "reference_name": {"type": "string"},
                "date": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.add_comment",
        "description": "Add a comment to an ERPNext document.",
        "parameters": _object_schema(
            ["reference_doctype", "reference_name", "content"],
            {"reference_doctype": {"type": "string"}, "reference_name": {"type": "string"}, "content": {"type": "string"}, "comment_email": {"type": "string"}, "comment_by": {"type": "string"}},
        ),
    },
    {
        "name": "erpnext.get_comments",
        "description": "List comments for an ERPNext document.",
        "parameters": _object_schema(["reference_doctype", "reference_name"], {"reference_doctype": {"type": "string"}, "reference_name": {"type": "string"}, "limit": {"type": "integer"}}),
    },
    {
        "name": "erpnext.assign_to",
        "description": "Assign an ERPNext document to one or more users.",
        "parameters": _object_schema(
            ["doctype", "name", "assign_to"],
            {"doctype": {"type": "string"}, "name": {"type": "string"}, "assign_to": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"}, "priority": {"type": "string"}, "date": {"type": "string"}},
        ),
    },
    {
        "name": "erpnext.clear_assignment",
        "description": "Remove or cancel an assignment for an ERPNext document.",
        "parameters": _object_schema(["doctype", "name", "assign_to"], {"doctype": {"type": "string"}, "name": {"type": "string"}, "assign_to": {"type": "string"}}),
    },
    {
        "name": "erpnext.attach_file",
        "description": "Attach a local file to an ERPNext document.",
        "parameters": _object_schema(["doctype", "name", "file_path"], {"doctype": {"type": "string"}, "name": {"type": "string"}, "file_path": {"type": "string"}, "is_private": {"type": "boolean"}, "fieldname": {"type": "string"}}),
    },
    {
        "name": "erpnext.list_attachments",
        "description": "List files attached to an ERPNext document.",
        "parameters": _object_schema(["doctype", "name"], {"doctype": {"type": "string"}, "name": {"type": "string"}}),
    },
    {
        "name": "erpnext.delete_attachment",
        "description": "Delete an ERPNext File attachment by File document name.",
        "parameters": _object_schema(["file_name"], {"file_name": {"type": "string"}}),
    },
    {
        "name": "erpnext.call_method",
        "description": "Call a whitelisted Frappe method. Prefer dedicated tools when available.",
        "parameters": _object_schema(["method"], {"method": {"type": "string"}, "args": {"type": "object"}, "http_method": {"enum": ["GET", "POST"]}, "confirmation": CONFIRMATION_SCHEMA}),
    },
]

GENERIC_TOOL_SCHEMAS = GENERIC_CORE_TOOL_SCHEMAS + GENERIC_AGENT_TOOL_SCHEMAS
