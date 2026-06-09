from __future__ import annotations


def _object_schema(required: list[str], properties: dict) -> dict:
    return {"type": "object", "required": required, "properties": properties}


BUYING_ITEM_LINE_SCHEMA = {
    "type": "object",
    "required": ["qty"],
    "properties": {
        "item_code": {"type": "string", "description": "ERPNext Item code. Must resolve to an existing Item."},
        "item_query": {"type": "string", "description": "Raw material name/spec query used when item_code is not provided."},
        "selected_item_code": {"type": "string", "description": "Confirmed candidate item_code returned by erpnext.search_items."},
        "selection_confirmed": {"type": "boolean", "description": "True only when a human or upstream policy confirmed the selected candidate."},
        "qty": {"type": "number", "exclusiveMinimum": 0},
        "uom": {"type": "string"},
        "schedule_date": {"type": "string"},
        "required_by": {"type": "string"},
        "warehouse": {"type": "string"},
        "rate": {"type": "number", "minimum": 0},
        "price_list_rate": {"type": "number", "minimum": 0},
        "conversion_factor": {"type": "number", "exclusiveMinimum": 0},
        "purchase_order": {"type": "string"},
        "purchase_order_item": {"type": "string"},
        "material_request": {"type": "string"},
        "material_request_item": {"type": "string"},
        "request_for_quotation": {"type": "string"},
        "supplier_quotation": {"type": "string"},
        "description": {"type": "string"},
    },
}

STOCK_ENTRY_ITEM_SCHEMA = {
    "type": "object",
    "required": ["qty"],
    "properties": {
        "item_code": {"type": "string", "description": "ERPNext Item code. Preferred when already confirmed."},
        "item_query": {"type": "string", "description": "Raw material query used when item_code is not available."},
        "selected_item_code": {"type": "string", "description": "Confirmed item_code from erpnext.stock.resolve_item."},
        "selection_confirmed": {"type": "boolean", "description": "True only after a human/upstream policy confirmed selected_item_code."},
        "s_warehouse": {"type": "string", "description": "Source warehouse for material issue/transfer."},
        "t_warehouse": {"type": "string", "description": "Target warehouse for material receipt/transfer."},
        "qty": {"type": "number", "exclusiveMinimum": 0},
        "uom": {"type": "string"},
        "stock_uom": {"type": "string"},
        "conversion_factor": {"type": "number", "exclusiveMinimum": 0},
        "basic_rate": {"type": "number", "minimum": 0},
        "batch_no": {"type": "string"},
        "serial_no": {"type": "string"},
        "expense_account": {"type": "string"},
        "cost_center": {"type": "string"},
        "description": {"type": "string"},
    },
}


STOCK_RECONCILIATION_ITEM_SCHEMA = {
    "type": "object",
    "required": ["warehouse"],
    "properties": {
        "item_code": {"type": "string"},
        "item_query": {"type": "string"},
        "selected_item_code": {"type": "string"},
        "selection_confirmed": {"type": "boolean"},
        "warehouse": {"type": "string"},
        "qty": {"type": "number", "minimum": 0},
        "valuation_rate": {"type": "number", "minimum": 0},
        "batch_no": {"type": "string"},
        "serial_no": {"type": "string"},
        "current_qty": {"type": "number"},
        "current_valuation_rate": {"type": "number"},
    },
}

PICK_LIST_LOCATION_SCHEMA = {
    "type": "object",
    "required": ["qty"],
    "properties": {
        "item_code": {"type": "string"},
        "item_query": {"type": "string"},
        "selected_item_code": {"type": "string"},
        "selection_confirmed": {"type": "boolean"},
        "warehouse": {"type": "string"},
        "qty": {"type": "number", "exclusiveMinimum": 0},
        "stock_qty": {"type": "number", "minimum": 0},
        "stock_uom": {"type": "string"},
        "batch_no": {"type": "string"},
        "serial_no": {"type": "string"},
        "sales_order_item": {"type": "string"},
        "material_request_item": {"type": "string"},
        "picked_qty": {"type": "number", "minimum": 0},
        "description": {"type": "string"},
    },
}

STOCK_PREVIEW_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "item_code": {"type": "string"},
        "item_query": {"type": "string"},
        "selected_item_code": {"type": "string"},
        "selection_confirmed": {"type": "boolean"},
        "warehouse": {"type": "string"},
        "qty": {"type": "number"},
        "qty_delta": {"type": "number"},
        "required_qty": {"type": "number", "minimum": 0},
        "incoming_rate": {"type": "number", "minimum": 0},
        "valuation_rate": {"type": "number", "minimum": 0},
        "voucher_type": {"type": "string"},
        "voucher_no": {"type": "string"},
        "voucher_detail_no": {"type": "string"},
    },
}


CONFIRMATION_SCHEMA = {
    "type": "object",
    "required": ["confirmed_by", "confirmed_at", "confirmation_text", "reason"],
    "properties": {
        "confirmed": {"type": "boolean"},
        "confirmed_by": {"type": "string"},
        "confirmed_at": {"type": "string"},
        "confirmation_text": {"type": "string"},
        "reason": {"type": "string"},
        "approval_reference": {"type": "string"},
    },
}


ERPNext_TOOL_SCHEMAS = [
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
    {
        "name": "erpnext.accounting.search_accounts",
        "description": "Read-only search for ERPNext Account rows by company, account type, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "account_type": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_cost_centers",
        "description": "Read-only search for ERPNext Cost Center rows by company, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_budgets",
        "description": "Read-only search for ERPNext Budget rows by company, fiscal year, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "fiscal_year": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_fiscal_years",
        "description": "Read-only search for ERPNext Fiscal Year records by year, disabled flag, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "year": {"type": "string"},
                "disabled": {"type": "boolean"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_accounting_periods",
        "description": "Read-only search for ERPNext Accounting Period records by company/date range, filters, pagination, and ordering.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_payment_terms",
        "description": "Read-only search for Payment Term or Payment Terms Template records.",
        "parameters": _object_schema(
            [],
            {
                "doctype": {"enum": ["Payment Term", "Payment Terms Template"]},
                "query": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.search_tax_templates",
        "description": "Read-only search for Sales or Purchase Taxes and Charges Template records.",
        "parameters": _object_schema(
            [],
            {
                "template_type": {"enum": ["sales", "purchase", "Sales Invoice", "Purchase Invoice"]},
                "query": {"type": "string"},
                "company": {"type": "string"},
                "tax_category": {"type": "string"},
                "disabled": {"type": "boolean"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.get_report_filters",
        "description": "Read-only accounting helper. Return the supported filter contract for a standard accounting report without running the report.",
        "parameters": _object_schema(
            ["report_name"],
            {
                "report_name": {
                    "enum": [
                        "General Ledger",
                        "Accounts Receivable",
                        "Accounts Payable",
                        "Trial Balance",
                        "Balance Sheet",
                        "Profit and Loss Statement",
                        "Cash Flow",
                    ]
                }
            },
        ),
    },
    {
        "name": "erpnext.accounting.general_ledger",
        "description": "Run ERPNext General Ledger as a read-only normalized report.",
        "parameters": _object_schema([], {"company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "account": {"type": "string"}, "party_type": {"type": "string"}, "party": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.accounts_receivable",
        "description": "Run ERPNext Accounts Receivable as a read-only normalized report.",
        "parameters": _object_schema([], {"company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "party": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.accounts_payable",
        "description": "Run ERPNext Accounts Payable as a read-only normalized report.",
        "parameters": _object_schema([], {"company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "party": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.financial_report",
        "description": "Run an allowed read-only ERPNext financial report: Trial Balance, Balance Sheet, Profit and Loss Statement, or Cash Flow.",
        "parameters": _object_schema(["report_name"], {"report_name": {"enum": ["Trial Balance", "Balance Sheet", "Profit and Loss Statement", "Cash Flow"]}, "company": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "fiscal_year": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_journal_entry_draft",
        "description": "Create a Journal Entry draft only. Submitting the voucher is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_payment_entry_draft",
        "description": "Create a Payment Entry draft only. Submitting the payment is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_sales_invoice_draft",
        "description": "Create a Sales Invoice draft only. Submitting the invoice is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_purchase_invoice_draft",
        "description": "Create a Purchase Invoice draft only. Submitting the invoice is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.create_period_closing_voucher_draft",
        "description": "Create a Period Closing Voucher draft only. Submitting period close is a separate high-risk financial action requiring confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.prepare_payment_allocation",
        "description": "L1 read-only helper. Prepare Payment Entry reference allocations for submitted Sales/Purchase Invoices without creating or submitting payment.",
        "parameters": _object_schema(
            ["party_type", "party"],
            {
                "party_type": {"enum": ["Customer", "Supplier"]},
                "party": {"type": "string"},
                "payment_type": {"enum": ["Receive", "Pay"]},
                "invoice_doctype": {"enum": ["Sales Invoice", "Purchase Invoice"]},
                "invoice_names": {"type": "array", "items": {"type": "string"}},
                "company": {"type": "string"},
                "paid_amount": {"type": "number", "minimum": 0},
                "allocations": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.prepare_invoice_taxes",
        "description": "L1 helper. Prepare invoice tax rows from a Sales/Purchase tax template or explicit tax rows; ERPNext still validates final totals on draft creation.",
        "parameters": _object_schema(
            ["invoice_type"],
            {
                "invoice_type": {"enum": ["sales", "purchase", "Sales Invoice", "Purchase Invoice"]},
                "taxes_and_charges": {"type": "string"},
                "items": {"type": "array", "items": {"type": "object"}},
                "taxes": {"type": "array", "items": {"type": "object"}},
                "net_total": {"type": "number", "minimum": 0},
            },
        ),
    },
    {
        "name": "erpnext.accounting.prepare_bank_reconciliation",
        "description": "L1 read-only helper. Gather Bank Transaction and Payment Entry candidates for reconciliation review without matching or posting.",
        "parameters": _object_schema(
            [],
            {
                "company": {"type": "string"},
                "bank_account": {"type": "string"},
                "status": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.accounting.apply_bank_reconciliation",
        "description": "L5_FINANCIAL. Match existing ERPNext payment documents to one Bank Transaction through agent_bridge after explicit finance confirmation. Does not create new payments or journal entries.",
        "parameters": _object_schema(
            ["bank_transaction", "matches", "confirmation"],
            {
                "bank_transaction": {"type": "string"},
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["payment_document", "payment_entry", "allocated_amount"],
                        "properties": {
                            "payment_document": {"type": "string"},
                            "payment_entry": {"type": "string"},
                            "allocated_amount": {"type": "number", "exclusiveMinimum": 0},
                        },
                    },
                },
                "replace_existing": {"type": "boolean"},
                "remarks": {"type": "string"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
    {
        "name": "erpnext.accounting.create_budget_draft",
        "description": "Create a Budget draft with docstatus forced to 0. Budget submission, if used, remains a separate reviewed action.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.update_budget_draft",
        "description": "Update a Budget draft with docstatus forced to 0. Does not submit budget controls.",
        "parameters": _object_schema(["name", "data"], {"name": {"type": "string"}, "data": {"type": "object"}}),
    },
    {
        "name": "erpnext.accounting.submit_financial_document",
        "description": "L5_FINANCIAL. Submit a GL-impacting financial document only after explicit confirmation metadata is present.",
        "parameters": _object_schema(
            ["doctype", "name", "confirmation"],
            {
                "doctype": {"enum": ["Journal Entry", "Payment Entry", "Sales Invoice", "Purchase Invoice", "Period Closing Voucher"]},
                "name": {"type": "string"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
    {
        "name": "erpnext.assets.search_assets",
        "description": "Read-only L0 search for fixed Asset records by company, category, location, status, Item, custodian, or asset name query.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "company": {"type": "string"},
                "asset_category": {"type": "string"},
                "location": {"type": "string"},
                "status": {"type": "string"},
                "item_code": {"type": "string"},
                "custodian": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.assets.search_asset_categories",
        "description": "Read-only L0 search for Asset Category master records.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.assets.search_asset_locations",
        "description": "Read-only L0 search for Asset Location records.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "filters": {"type": ["object", "array"]},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.assets.get_financial_snapshot",
        "description": "Read-only L0 snapshot of one Asset's purchase, finance book, depreciation, and linked Asset Depreciation Schedule state. Does not post depreciation, create GL entries, or create sale/disposal documents.",
        "parameters": _object_schema(
            ["asset"],
            {
                "asset": {"type": "string"},
                "finance_book": {"type": "string"},
                "include_depreciation_schedules": {"type": "boolean"},
                "include_schedule_rows": {"type": "boolean"},
                "schedule_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        ),
    },
    {
        "name": "erpnext.assets.get_depreciation_schedule",
        "description": "Read-only L0 asset tool. List Asset Depreciation Schedule records and optionally expand due schedule rows without posting depreciation.",
        "parameters": _object_schema(
            ["asset"],
            {
                "asset": {"type": "string"},
                "finance_book": {"type": "string"},
                "status": {"type": "string"},
                "include_rows": {"type": "boolean"},
                "only_due_before": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.assets.create_asset_draft",
        "description": "Create an Asset draft only. Submitting/capitalizing the asset is L5_FINANCIAL and requires confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.assets.create_movement_draft",
        "description": "Create an Asset Movement draft for issue, receipt, or transfer. L3 draft only; submission is L4 and requires confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.assets.create_maintenance_draft",
        "description": "Create an Asset Maintenance plan draft. L3 draft only; submission is L4 and requires confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.assets.create_maintenance_log_draft",
        "description": "Create an Asset Maintenance Log draft. L3 draft only; submission is L4 and requires confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.assets.create_repair_draft",
        "description": "Create an Asset Repair draft. L3 draft only; submitted repair may affect asset value/costs and requires confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.assets.create_value_adjustment_draft",
        "description": "Create an Asset Value Adjustment draft. L3 draft only; submission is L5_FINANCIAL and requires confirmation metadata.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.assets.prepare_disposal_or_sale",
        "description": "Read-only L1 preparation for asset disposal or sale. Does not post GL or create invoices; returns next actions and risk context.",
        "parameters": _object_schema(
            ["asset"],
            {
                "asset": {"type": "string"},
                "action": {"enum": ["dispose", "scrap", "sell"]},
                "posting_date": {"type": "string"},
                "proceeds_amount": {"type": "number", "minimum": 0},
                "party_type": {"type": "string"},
                "party": {"type": "string"},
                "reason": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.assets.submit_document",
        "description": "Submit an asset lifecycle document after explicit high-risk confirmation metadata is present. Asset capitalization and value adjustment are L5_FINANCIAL; movement/maintenance/repair are L4.",
        "parameters": _object_schema(
            ["doctype", "name", "confirmation"],
            {
                "doctype": {"enum": ["Asset", "Asset Movement", "Asset Maintenance", "Asset Maintenance Log", "Asset Repair", "Asset Value Adjustment"]},
                "name": {"type": "string"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
    {
        "name": "erpnext.stock.get_balance",
        "description": "Read Bin stock balances by item and/or warehouse. Read-only L0 inventory quantity and valuation snapshot.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "warehouse": {"type": "string"},
                "specs": {"type": "object"},
                "item_group": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        ),
    },
    {
        "name": "erpnext.stock.get_item_locations",
        "description": "Find warehouses/Bins where one resolved Item has stock. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "selected_item_code": {"type": "string"},
                "selection_confirmed": {"type": "boolean"},
                "specs": {"type": "object"},
                "item_group": {"type": "string"},
                "include_zero": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        ),
    },
    {
        "name": "erpnext.stock.get_ledger_entries",
        "description": "Read Stock Ledger Entry rows for inventory movement audit. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "warehouse": {"type": "string"},
                "voucher_type": {"type": "string"},
                "voucher_no": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        ),
    },
    {
        "name": "erpnext.stock.get_stock_settings",
        "description": "Read the Stock Settings singleton for inventory control rules such as reservations, batches, serials, and valuation behavior. Read-only L0.",
        "parameters": _object_schema([], {}),
    },
    {
        "name": "erpnext.stock.resolve_item",
        "description": "Resolve a stock Item by first using optional PostgreSQL material catalog recall and then ERPNext Item search. L1 preparation; does not change ERPNext.",
        "parameters": _object_schema(
            ["query"],
            {
                "query": {"type": "string"},
                "specs": {"type": "object"},
                "item_group": {"type": "string"},
                "enabled_only": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "catalog_database_url": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.stock.create_entry_draft",
        "description": "Create a Stock Entry draft for material receipt, issue, transfer, manufacture, or repack. L3 draft only; submit is separate L4.",
        "parameters": _object_schema(
            ["items"],
            {
                "stock_entry_type": {"type": "string"},
                "purpose": {"type": "string"},
                "company": {"type": "string"},
                "posting_date": {"type": "string"},
                "posting_time": {"type": "string"},
                "remarks": {"type": "string"},
                "items": {"type": "array", "items": STOCK_ENTRY_ITEM_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.stock.create_reconciliation_draft",
        "description": "Create a Stock Reconciliation draft for physical count or inventory adjustment. L3 draft only; submission changes quantity/value and is L4.",
        "parameters": _object_schema(
            ["items"],
            {
                "company": {"type": "string"},
                "posting_date": {"type": "string"},
                "posting_time": {"type": "string"},
                "purpose": {"type": "string"},
                "expense_account": {"type": "string"},
                "cost_center": {"type": "string"},
                "remarks": {"type": "string"},
                "items": {"type": "array", "items": STOCK_RECONCILIATION_ITEM_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.stock.search_batches",
        "description": "Search Batch records by Item or batch query. Read-only L0; changing batches after movement is high risk and not wrapped here.",
        "parameters": _object_schema([], {"item_code": {"type": "string"}, "item_query": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
    },
    {
        "name": "erpnext.stock.list_batch_balances",
        "description": "Read-only L0 stock tool. Summarize Batch availability by Item, Batch, warehouse, and Stock Ledger Entry rows without moving stock.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "selected_item_code": {"type": "string"},
                "selection_confirmed": {"type": "boolean"},
                "batch_no": {"type": "string"},
                "query": {"type": "string"},
                "warehouse": {"type": "string"},
                "include_expired": {"type": "boolean"},
                "include_zero": {"type": "boolean"},
                "as_of_date": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "batch_limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "ledger_limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        ),
    },
    {
        "name": "erpnext.stock.search_serial_numbers",
        "description": "Search Serial No records by Item, warehouse, status, or serial query. Read-only L0.",
        "parameters": _object_schema([], {"item_code": {"type": "string"}, "item_query": {"type": "string"}, "warehouse": {"type": "string"}, "status": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
    },
    {
        "name": "erpnext.stock.create_batch",
        "description": "Create a Batch traceability record for an existing ERPNext Item. L3 traceability write; does not move stock.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.update_batch",
        "description": "Update a Batch traceability record. L4 because post-movement batch edits affect inventory traceability and require confirmation metadata.",
        "parameters": _object_schema(
            ["name", "data", "confirmation"],
            {"name": {"type": "string"}, "data": {"type": "object"}, "confirmation": CONFIRMATION_SCHEMA},
        ),
    },
    {
        "name": "erpnext.stock.create_serial_no",
        "description": "Create a Serial No traceability record for an existing ERPNext Item. L3 traceability write; does not submit stock movement.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.update_serial_no",
        "description": "Update a Serial No traceability record. L4 because post-movement serial edits affect inventory traceability and require confirmation metadata.",
        "parameters": _object_schema(
            ["name", "data", "confirmation"],
            {"name": {"type": "string"}, "data": {"type": "object"}, "confirmation": CONFIRMATION_SCHEMA},
        ),
    },
    {
        "name": "erpnext.stock.list_pick_lists",
        "description": "List Pick List documents for warehouse picking workflows. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "purpose": {"type": "string"},
                "status": {"type": "string"},
                "customer": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.stock.create_pick_list_draft",
        "description": "Create a Pick List draft for Delivery, Material Transfer, or Manufacture workflows. L3 draft only; submit is separate L4.",
        "parameters": _object_schema(
            [],
            {
                "purpose": {"type": "string"},
                "customer": {"type": "string"},
                "work_order": {"type": "string"},
                "material_request": {"type": "string"},
                "sales_order": {"type": "string"},
                "parent_warehouse": {"type": "string"},
                "locations": {"type": "array", "items": PICK_LIST_LOCATION_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.stock.list_reservations",
        "description": "List Stock Reservation Entry documents by item, warehouse, voucher, or status. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "warehouse": {"type": "string"},
                "voucher_type": {"type": "string"},
                "voucher_no": {"type": "string"},
                "status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.stock.create_reservation_draft",
        "description": "Create a Stock Reservation Entry draft for a resolved Item and source voucher. L3 draft only; submission affects available stock and is L4.",
        "parameters": _object_schema(
            ["warehouse", "reserved_qty"],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "selected_item_code": {"type": "string"},
                "selection_confirmed": {"type": "boolean"},
                "warehouse": {"type": "string"},
                "voucher_type": {"type": "string"},
                "voucher_no": {"type": "string"},
                "voucher_detail_no": {"type": "string"},
                "reserved_qty": {"type": "number", "exclusiveMinimum": 0},
                "company": {"type": "string"},
                "stock_uom": {"type": "string"},
                "from_voucher_type": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.stock.preview_valuation",
        "description": "Preview stock quantity/value impact through agent_bridge without creating Stock Entry or Stock Reconciliation. L1 read-only/preparation.",
        "parameters": _object_schema(
            ["items"],
            {"items": {"type": "array", "items": STOCK_PREVIEW_ITEM_SCHEMA}},
        ),
    },
    {
        "name": "erpnext.stock.allocate_shortages",
        "description": "Preview available stock allocation and shortage quantities through agent_bridge without creating reservations, pick lists, or purchase requests. L1 preparation.",
        "parameters": _object_schema(
            ["items"],
            {"items": {"type": "array", "items": STOCK_PREVIEW_ITEM_SCHEMA}},
        ),
    },
    {
        "name": "erpnext.stock.list_delivery_notes",
        "description": "List Delivery Note documents for stock-side impact review. Read-only L0; Sales owns Delivery Note draft/business workflow.",
        "parameters": _object_schema(
            [],
            {
                "customer": {"type": "string"},
                "status": {"type": "string"},
                "docstatus": {"type": "integer", "minimum": 0, "maximum": 2},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.stock.list_purchase_receipts",
        "description": "List Purchase Receipt documents for stock-side impact review. Read-only L0; Buying owns Purchase Receipt draft/business workflow.",
        "parameters": _object_schema(
            [],
            {
                "supplier": {"type": "string"},
                "status": {"type": "string"},
                "docstatus": {"type": "integer", "minimum": 0, "maximum": 2},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.stock.get_document_impact",
        "description": "Read stock ledger impact for a Delivery Note or Purchase Receipt without editing or creating cross-module documents. L0 boundary tool.",
        "parameters": _object_schema(
            ["doctype", "name"],
            {
                "doctype": {"enum": ["Delivery Note", "Purchase Receipt"]},
                "name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        ),
    },
    {
        "name": "erpnext.stock.list_item_reorders",
        "description": "List Item Reorder rows by Item, warehouse, or Material Request Type to inspect warehouse reorder thresholds. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "warehouse": {"type": "string"},
                "material_request_type": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        ),
    },
    {
        "name": "erpnext.stock.list_quality_inspections",
        "description": "List Quality Inspection documents connected to stock receipt, delivery, or item quality workflows. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "reference_type": {"type": "string"},
                "reference_name": {"type": "string"},
                "inspection_type": {"type": "string"},
                "status": {"type": "string"},
                "docstatus": {"type": "integer", "minimum": 0, "maximum": 2},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.stock.list_warehouses",
        "description": "List Warehouse records by company or name query. Read-only L0.",
        "parameters": _object_schema([], {"company": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    },
    {
        "name": "erpnext.stock.create_warehouse",
        "description": "Create a Warehouse master record. L3 master-data write; does not move stock.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.update_warehouse",
        "description": "Update a Warehouse master record. L3 master-data write; does not move stock.",
        "parameters": _object_schema(["name", "data"], {"name": {"type": "string"}, "data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.list_item_groups",
        "description": "List Item Group master records by parent, group flag, or name query. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "parent_item_group": {"type": "string"},
                "is_group": {"type": "boolean"},
                "filters": {"type": "object"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.stock.create_item_group",
        "description": "Create an Item Group master record. L3 master-data write; does not create Items or move stock.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.update_item_group",
        "description": "Update an Item Group master record. L3 master-data write; does not create Items or move stock.",
        "parameters": _object_schema(["name", "data"], {"name": {"type": "string"}, "data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.list_uoms",
        "description": "List UOM master records by enabled flag or name query. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "enabled": {"type": "boolean"},
                "filters": {"type": "object"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.stock.create_uom",
        "description": "Create a UOM master record. L3 master-data write; does not affect existing stock balances.",
        "parameters": _object_schema(["data"], {"data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.update_uom",
        "description": "Update a UOM master record. L3 master-data write; does not affect existing stock balances.",
        "parameters": _object_schema(["name", "data"], {"name": {"type": "string"}, "data": {"type": "object"}}),
    },
    {
        "name": "erpnext.stock.submit_document",
        "description": "Submit a stock-affecting document after explicit high-risk confirmation metadata is present. L4.",
        "parameters": _object_schema(
            ["doctype", "name", "confirmation"],
            {
                "doctype": {"enum": ["Stock Entry", "Stock Reconciliation", "Delivery Note", "Purchase Receipt", "Pick List", "Stock Reservation Entry"]},
                "name": {"type": "string"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
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
    {
        "name": "erpnext.buying.search_suppliers",
        "description": "Search Supplier records by supplier name/group/type with safe fields for buying workflows.",
        "parameters": _object_schema(
            [],
            {
                "query": {"type": "string"},
                "supplier_group": {"type": "string"},
                "supplier_type": {"type": "string"},
                "disabled": {"type": "boolean"},
                "is_frozen": {"type": "boolean"},
                "on_hold": {"type": "boolean"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.buying.search_supplier_scorecards",
        "description": "Read-only L0 search for Supplier Scorecard rows and RFQ/PO warning or prevention flags.",
        "parameters": _object_schema(
            [],
            {
                "supplier": {"type": "string"},
                "status": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order_by": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.buying.get_supplier_procurement_profile",
        "description": "L1 procurement helper. Read Supplier, scorecards, optional item supplier and item price context to decide whether RFQ/PO should be blocked, warned, or allowed.",
        "parameters": _object_schema(
            ["supplier"],
            {
                "supplier": {"type": "string"},
                "company": {"type": "string"},
                "item_code": {"type": "string"},
                "currency": {"type": "string"},
                "price_list": {"type": "string"},
                "scorecard_limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
        ),
    },
    {
        "name": "erpnext.buying.create_supplier_group_draft",
        "description": "Create a Supplier Group draft/master record.",
        "parameters": _object_schema(
            ["supplier_group_name"],
            {
                "supplier_group_name": {"type": "string"},
                "parent_supplier_group": {"type": "string"},
                "is_group": {"type": "boolean"},
            },
        ),
    },
    {
        "name": "erpnext.buying.create_supplier_draft",
        "description": "Create a Supplier draft/master record without submitting any transaction.",
        "parameters": _object_schema(
            ["supplier_name"],
            {
                "supplier_name": {"type": "string"},
                "supplier_group": {"type": "string"},
                "supplier_type": {"type": "string"},
                "country": {"type": "string"},
                "tax_id": {"type": "string"},
                "default_currency": {"type": "string"},
            },
        ),
    },
    {
        "name": "erpnext.buying.create_material_request_draft",
        "description": "Create a Purchase Material Request draft. Item rows must resolve through ERPNext Item/material search.",
        "parameters": _object_schema(
            ["items"],
            {
                "material_request_type": {"type": "string"},
                "schedule_date": {"type": "string"},
                "company": {"type": "string"},
                "items": {"type": "array", "items": BUYING_ITEM_LINE_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.buying.create_request_for_quotation_draft",
        "description": "Create a Request for Quotation draft with suppliers and resolved item rows.",
        "parameters": _object_schema(
            ["suppliers", "items"],
            {
                "transaction_date": {"type": "string"},
                "schedule_date": {"type": "string"},
                "company": {"type": "string"},
                "message_for_supplier": {"type": "string"},
                "suppliers": {"type": "array", "items": {"type": "object"}},
                "items": {"type": "array", "items": BUYING_ITEM_LINE_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.buying.create_supplier_quotation_draft",
        "description": "Create a Supplier Quotation draft from a supplier and resolved item rows.",
        "parameters": _object_schema(
            ["supplier", "items"],
            {
                "supplier": {"type": "string"},
                "transaction_date": {"type": "string"},
                "valid_till": {"type": "string"},
                "company": {"type": "string"},
                "currency": {"type": "string"},
                "buying_price_list": {"type": "string"},
                "items": {"type": "array", "items": BUYING_ITEM_LINE_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.buying.create_purchase_order_draft",
        "description": "Create a Purchase Order draft. Does not submit business commitment.",
        "parameters": _object_schema(
            ["supplier", "items"],
            {
                "supplier": {"type": "string"},
                "schedule_date": {"type": "string"},
                "transaction_date": {"type": "string"},
                "company": {"type": "string"},
                "currency": {"type": "string"},
                "buying_price_list": {"type": "string"},
                "items": {"type": "array", "items": BUYING_ITEM_LINE_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.buying.create_purchase_receipt_draft",
        "description": "Create a Purchase Receipt draft for received purchasing items. Does not submit stock movement.",
        "parameters": _object_schema(
            ["supplier", "items"],
            {
                "supplier": {"type": "string"},
                "posting_date": {"type": "string"},
                "company": {"type": "string"},
                "items": {"type": "array", "items": BUYING_ITEM_LINE_SCHEMA},
            },
        ),
    },
    {
        "name": "erpnext.buying.generate_purchase_suggestions",
        "description": "Generate low-stock purchase suggestions through agent_bridge business logic.",
        "parameters": _object_schema([], {"limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    },
    {
        "name": "erpnext.buying.search_item_suppliers",
        "description": "Search Item Supplier rows by parent Item or Supplier.",
        "parameters": _object_schema(
            [],
            {"item_code": {"type": "string"}, "supplier": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
        ),
    },
    {
        "name": "erpnext.buying.search_item_prices",
        "description": "Search buying Item Price rows by item, price list, supplier, currency, and validity.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "price_list": {"type": "string"},
                "supplier": {"type": "string"},
                "currency": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        ),
    },
    {
        "name": "erpnext.buying.get_buying_settings",
        "description": "Read Buying Settings singleton.",
        "parameters": _object_schema([], {}),
    },
    {
        "name": "erpnext.buying.run_purchase_analysis",
        "description": "Run a standard purchase analysis report through the normalized report tool.",
        "parameters": _object_schema([], {"report_name": {"type": "string"}, "filters": {"type": "object"}}),
    },
    {
        "name": "erpnext.buying.compare_supplier_quotations",
        "description": "L1 preview. Compare Supplier Quotation totals and item rates without awarding business or creating a Purchase Order.",
        "parameters": _object_schema(
            ["supplier_quotations"],
            {
                "supplier_quotations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "description": "Supplier Quotation document names to compare.",
                },
                "include_drafts": {"type": "boolean", "description": "Include draft Supplier Quotations for preview; defaults to false."},
            },
        ),
    },
    {
        "name": "erpnext.buying.submit_document",
        "description": "Submit a buying document after explicit high-risk confirmation metadata is present.",
        "parameters": _object_schema(
            ["doctype", "name", "confirmation"],
            {
                "doctype": {"enum": ["Material Request", "Request for Quotation", "Supplier Quotation", "Purchase Order", "Purchase Receipt"]},
                "name": {"type": "string"},
                "confirmation": CONFIRMATION_SCHEMA,
            },
        ),
    },
]
