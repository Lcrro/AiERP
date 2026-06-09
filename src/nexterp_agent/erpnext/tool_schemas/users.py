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

USERS_TOOL_SCHEMAS = [
    {
        "name": "erpnext.users.list_users",
        "description": "Read-only Users & Permissions tool. List ERPNext User records with safe identity/status fields.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "enabled": {"type": "boolean"},
                "user_type": {"type": "string"},
                "role_profile_name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
            },
        ),
    },
    {
        "name": "erpnext.users.get_user_access_summary",
        "description": "Read-only Users & Permissions tool. Get a user with roles, role profile, direct user permissions, and basic status.",
        "parameters": _object_schema(["user"], {"user": {"type": "string"}, "include_permissions": {"type": "boolean"}}),
    },
    {
        "name": "erpnext.users.list_roles",
        "description": "Read-only Users & Permissions tool. List Role records.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "disabled": {"type": "boolean"},
                "desk_access": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
            },
        ),
    },
    {
        "name": "erpnext.users.list_role_profiles",
        "description": "Read-only Users & Permissions tool. List Role Profile records.",
        "parameters": _object_schema([], {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "offset": {"type": "integer", "minimum": 0}}),
    },
    {
        "name": "erpnext.users.preview_role_profile_roles",
        "description": "Read-only Users & Permissions tool. Expand one Role Profile into its roles before assigning it to a user.",
        "parameters": _object_schema(["role_profile"], {"role_profile": {"type": "string"}}),
    },
    {
        "name": "erpnext.users.list_user_permissions",
        "description": "Read-only Users & Permissions tool. List User Permission records by user, allowed DocType, or allowed value.",
        "parameters": _object_schema(
            [],
            {
                "user": {"type": "string"},
                "allow": {"type": "string"},
                "for_value": {"type": "string"},
                "applicable_for": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
            },
        ),
    },
    {
        "name": "erpnext.users.list_shared_documents",
        "description": "Read-only Users & Permissions tool. List DocShare rows for a user or shared document.",
        "parameters": _object_schema(
            [],
            {
                "user": {"type": "string"},
                "share_doctype": {"type": "string"},
                "share_name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
            },
        ),
    },
    {
        "name": "erpnext.users.list_access_logs",
        "description": "Read-only Users & Permissions tool. List Access Log rows for audit review.",
        "parameters": _object_schema([], {"user": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "offset": {"type": "integer", "minimum": 0}}),
    },
    {
        "name": "erpnext.users.list_activity_logs",
        "description": "Read-only Users & Permissions tool. List Activity Log rows for audit review.",
        "parameters": _object_schema([], {"user": {"type": "string"}, "subject": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "offset": {"type": "integer", "minimum": 0}}),
    },
    {
        "name": "erpnext.users.get_permission_metadata",
        "description": "Read-only Users & Permissions tool. Inspect DocPerm/Custom DocPerm style permission metadata for a DocType.",
        "parameters": _object_schema(["doctype"], {"doctype": {"type": "string"}}),
    },
    {
        "name": "erpnext.users.preview_effective_permissions",
        "description": "Read-only Users & Permissions tool. Preview a user's likely permissions on one DocType from DocType permission metadata and direct User Permission rows. This is not exact server-side runtime evaluation.",
        "parameters": _object_schema(
            ["user", "doctype"],
            {
                "user": {"type": "string"},
                "doctype": {"type": "string"},
                "include_user_permissions": {"type": "boolean"},
            },
        ),
    },
    {
        "name": "erpnext.users.check_server_permission",
        "description": "Read-only Users & Permissions tool. Ask agent_bridge to run Frappe's server-side permission engine for one user, DocType, optional document, and action, then compare it with metadata preview.",
        "parameters": _object_schema(
            ["user", "doctype", "action"],
            {
                "user": {"type": "string"},
                "doctype": {"type": "string"},
                "docname": {"type": "string"},
                "action": {
                    "enum": [
                        "select",
                        "read",
                        "write",
                        "create",
                        "delete",
                        "submit",
                        "cancel",
                        "amend",
                        "report",
                        "export",
                        "import",
                        "share",
                        "print",
                        "email",
                    ]
                },
                "debug": {"type": "boolean"},
            },
        ),
    },
    {
        "name": "erpnext.users.preview_permission_policy_change",
        "description": "L5_ADMIN preview-only Users & Permissions tool. Simulate add/update/remove changes to DocPerm-style permission rows for one DocType and return before/after/diff without writing ERPNext.",
        "parameters": _object_schema(
            ["doctype", "changes"],
            {
                "doctype": {"type": "string"},
                "changes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["operation"],
                        "properties": {
                            "operation": {"enum": ["add", "update", "remove"]},
                            "role": {"type": "string"},
                            "permlevel": {"type": "integer", "minimum": 0},
                            "match": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "role": {"type": "string"},
                                    "permlevel": {"type": "integer", "minimum": 0},
                                },
                            },
                            "permissions": {
                                "type": "object",
                                "properties": {
                                    "select": {"type": "boolean"},
                                    "read": {"type": "boolean"},
                                    "write": {"type": "boolean"},
                                    "create": {"type": "boolean"},
                                    "delete": {"type": "boolean"},
                                    "submit": {"type": "boolean"},
                                    "cancel": {"type": "boolean"},
                                    "amend": {"type": "boolean"},
                                    "report": {"type": "boolean"},
                                    "export": {"type": "boolean"},
                                    "import": {"type": "boolean"},
                                    "share": {"type": "boolean"},
                                    "print": {"type": "boolean"},
                                    "email": {"type": "boolean"},
                                    "if_owner": {"type": "boolean"},
                                    "apply_user_permissions": {"type": "boolean"},
                                },
                            },
                        },
                    },
                },
            },
        ),
    },
    {
        "name": "erpnext.users.create_user_draft",
        "description": "L5_ADMIN. Create a User master record with enabled=false by default and welcome email disabled. Requires explicit confirmation metadata.",
        "parameters": _object_schema(
            ["email", "first_name", "confirmation"],
            {
                "email": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "user_type": {"type": "string"},
                "role_profile_name": {"type": "string"},
                "roles": {"type": "array", "items": {"type": "string"}},
                "enabled": {"type": "boolean"},
                "send_welcome_email": {"type": "boolean"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
    {
        "name": "erpnext.users.set_user_enabled",
        "description": "L5_ADMIN. Enable or disable a User. Requires explicit confirmation metadata.",
        "parameters": _object_schema(["user", "enabled", "confirmation"], {"user": {"type": "string"}, "enabled": {"type": "boolean"}, "confirmation": CONFIRMATION_SCHEMA}),
    },
    {
        "name": "erpnext.users.assign_roles",
        "description": "L5_ADMIN. Replace, add, or remove roles on a User. Requires explicit confirmation metadata.",
        "parameters": _object_schema(
            ["user", "mode", "roles", "confirmation"],
            {"user": {"type": "string"}, "mode": {"enum": ["replace", "add", "remove"]}, "roles": {"type": "array", "items": {"type": "string"}}, "confirmation": CONFIRMATION_SCHEMA},
        ),
    },
    {
        "name": "erpnext.users.create_user_permission",
        "description": "L5_ADMIN. Create a User Permission row. Requires explicit confirmation metadata.",
        "parameters": _object_schema(
            ["user", "allow", "for_value", "confirmation"],
            {
                "user": {"type": "string"},
                "allow": {"type": "string"},
                "for_value": {"type": "string"},
                "applicable_for": {"type": "string"},
                "is_default": {"type": "boolean"},
                "hide_descendants": {"type": "boolean"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
    {
        "name": "erpnext.users.delete_user_permission",
        "description": "L5_ADMIN. Delete a User Permission row by name. Requires explicit confirmation metadata.",
        "parameters": _object_schema(["name", "confirmation"], {"name": {"type": "string"}, "confirmation": CONFIRMATION_SCHEMA}),
    },
]
