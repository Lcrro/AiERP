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

ASSETS_TOOL_SCHEMAS = [
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
]
