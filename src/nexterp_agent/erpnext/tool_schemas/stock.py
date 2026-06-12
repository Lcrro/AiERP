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

STOCK_TOOL_SCHEMAS = [
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
        "name": "erpnext.stock.create_quality_inspection_draft",
        "description": "Create a Quality Inspection draft for incoming/outgoing/process inspection. L3 draft only; submit is separate if needed.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "selected_item_code": {"type": "string"},
                "selection_confirmed": {"type": "boolean"},
                "inspection_type": {"type": "string"},
                "reference_type": {"type": "string"},
                "reference_name": {"type": "string"},
                "sample_size": {"type": "number", "minimum": 0},
                "inspected_by": {"type": "string"},
                "verified_by": {"type": "string"},
                "report_date": {"type": "string"},
                "status": {"type": "string"},
                "remarks": {"type": "string"},
                "readings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "specification": {"type": "string"},
                            "value": {"type": "string"},
                            "status": {"type": "string"},
                            "numeric_value": {"type": "number"},
                            "min_value": {"type": "number"},
                            "max_value": {"type": "number"},
                        },
                    },
                },
            },
        ),
    },
    {
        "name": "erpnext.stock.verify_purchase_receipt_stock_impact",
        "description": "Verify a submitted Purchase Receipt against Stock Ledger Entry rows and summarize received quantity/value impact. Read-only L0.",
        "parameters": _object_schema(
            ["purchase_receipt"],
            {
                "purchase_receipt": {"type": "string"},
                "item_code": {"type": "string"},
                "warehouse": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        ),
    },
    {
        "name": "erpnext.stock.get_item_lifecycle_summary",
        "description": "Read a material lifecycle summary across Item, Purchase Receipt items, Stock Ledger, Quality Inspection, Stock Entry details, and Purchase Invoice items. Read-only L0.",
        "parameters": _object_schema(
            [],
            {
                "item_code": {"type": "string"},
                "item_query": {"type": "string"},
                "selected_item_code": {"type": "string"},
                "selection_confirmed": {"type": "boolean"},
                "project": {"type": "string"},
                "warehouse": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
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
]
