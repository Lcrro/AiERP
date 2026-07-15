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
        "project": {"type": "string"},
        "cost_center": {"type": "string"},
        "rate": {"type": "number", "minimum": 0},
        "price_list_rate": {"type": "number", "minimum": 0},
        "conversion_factor": {"type": "number", "exclusiveMinimum": 0},
        "purchase_order": {"type": "string"},
        "purchase_order_item": {"type": "string"},
        "material_request": {"type": "string"},
        "material_request_item": {"type": "string"},
        "request_for_quotation": {"type": "string"},
        "request_for_quotation_item": {"type": "string"},
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
