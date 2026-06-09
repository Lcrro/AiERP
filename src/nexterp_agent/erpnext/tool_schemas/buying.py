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

BUYING_TOOL_SCHEMAS = [
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
