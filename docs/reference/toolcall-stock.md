# ERPNext Stock ToolCall Coverage

Scope: Stock / 库存.

This document records the v0.2 module-aware ToolCall surface for Item inventory,
warehouses, Bin balances, Stock Entry, Stock Reconciliation, Batch, Serial No,
and Stock Ledger Entry analysis.

## Core DocTypes

| Capability | ERPNext DocTypes |
| --- | --- |
| Item master integration | `Item`, `Item Group`, `UOM` |
| Warehouse structure | `Warehouse` |
| Current stock balance | `Bin` |
| Stock policy/settings | `Stock Settings`, `Item Reorder` |
| Inventory movement | `Stock Entry`, `Stock Entry Detail` |
| Physical count / adjustment | `Stock Reconciliation`, `Stock Reconciliation Item` |
| Traceability | `Batch`, `Serial No` |
| Quality gate | `Quality Inspection` |
| Movement audit | `Stock Ledger Entry` |
| Cross-module stock effects | `Purchase Receipt`, `Delivery Note` |

## Implemented Tools

Read-only Stock tools:

| Tool | ERPNext surface | Risk | Notes |
| --- | --- | --- | --- |
| `erpnext.stock.get_balance` | `Bin` | `L0` | Query balance by `item_code` and/or `warehouse`; can resolve a ready `item_query`. |
| `erpnext.stock.get_item_locations` | `Bin` | `L0` | Finds warehouses where one resolved Item has stock; excludes zero balances by default. |
| `erpnext.stock.get_ledger_entries` | `Stock Ledger Entry` | `L0` | Read-only movement and valuation audit rows. |
| `erpnext.stock.get_stock_settings` | `Stock Settings` | `L0` | Reads global stock policy/settings such as negative stock, serial/batch behavior, and reservation context. |
| `erpnext.stock.search_batches` | `Batch` | `L0` | Batch lookup by item or batch query. |
| `erpnext.stock.list_batch_balances` | `Batch`, `Stock Ledger Entry` | `L0` | Summarizes batch availability by item, batch, warehouse, and ledger rows; does not move stock. |
| `erpnext.stock.search_serial_numbers` | `Serial No` | `L0` | Serial lookup by item, warehouse, status, or serial query. |
| `erpnext.stock.list_warehouses` | `Warehouse` | `L0` | Warehouse tree/list lookup by company or name query. |
| `erpnext.stock.list_item_groups` | `Item Group` | `L0` | Item Group tree/list lookup by parent, group flag, or name query. |
| `erpnext.stock.list_uoms` | `UOM` | `L0` | UOM lookup by enabled flag or name query. |
| `erpnext.stock.list_pick_lists` | `Pick List` | `L0` | Pick-list workflow lookup by purpose, status, or customer. |
| `erpnext.stock.list_reservations` | `Stock Reservation Entry` | `L0` | Reservation lookup by item, warehouse, voucher, or status. |
| `erpnext.stock.list_delivery_notes` | `Delivery Note` | `L0` | Stock-side read-only review; Sales owns draft/business workflow. |
| `erpnext.stock.list_purchase_receipts` | `Purchase Receipt` | `L0` | Stock-side read-only review; Buying owns draft/business workflow. |
| `erpnext.stock.get_document_impact` | `Delivery Note`, `Purchase Receipt`, `Stock Ledger Entry` | `L0` | Reads document summary plus stock ledger impact; does not edit or create cross-module documents. |
| `erpnext.stock.list_item_reorders` | `Item Reorder` | `L0` | Reads reorder thresholds and reorder quantities by item, warehouse, or material request type. |
| `erpnext.stock.list_quality_inspections` | `Quality Inspection` | `L0` | Reads incoming/outgoing/in-process quality inspection rows by item, reference document, status, or docstatus. |

Preparation and draft tools:

| Tool | ERPNext surface | Risk | Notes |
| --- | --- | --- | --- |
| `erpnext.stock.resolve_item` | PostgreSQL catalog + ERPNext `Item` | `L1` | Uses optional PostgreSQL material catalog recall, then ERPNext Item search as source of truth. |
| `erpnext.stock.preview_valuation` | `agent_bridge.api.preview_stock_valuation` | `L1` | Preview quantity/value impact from Bin valuation without creating stock documents. |
| `erpnext.stock.allocate_shortages` | `agent_bridge.api.allocate_stock_shortages` | `L1` | Preview available allocation and shortage quantities without creating reservations, pick lists, or purchase requests. |
| `erpnext.stock.create_entry_draft` | `Stock Entry` | `L3` | Draft only. Does not submit movement. |
| `erpnext.stock.create_reconciliation_draft` | `Stock Reconciliation` | `L3` | Draft only. Submission changes quantity/value. |
| `erpnext.stock.create_warehouse` | `Warehouse` | `L3` | Master data write; no stock movement. |
| `erpnext.stock.update_warehouse` | `Warehouse` | `L3` | Master data write; no stock movement. |
| `erpnext.stock.create_item_group` | `Item Group` | `L3` | Master data write; no stock movement. |
| `erpnext.stock.update_item_group` | `Item Group` | `L3` | Master data write; no stock movement. |
| `erpnext.stock.create_uom` | `UOM` | `L3` | Master data write; no stock movement. |
| `erpnext.stock.update_uom` | `UOM` | `L3` | Master data write; no stock movement. |
| `erpnext.stock.create_batch` | `Batch` | `L3` | Traceability write for an existing Item; no stock movement. |
| `erpnext.stock.create_serial_no` | `Serial No` | `L3` | Traceability write for an existing Item; no stock movement. |
| `erpnext.stock.create_pick_list_draft` | `Pick List` | `L3` | Draft picking workflow for Delivery, Material Transfer, or Manufacture; submit is L4. |
| `erpnext.stock.create_reservation_draft` | `Stock Reservation Entry` | `L3` | Draft reservation for a resolved Item and source voucher; submit affects available stock and is L4. |

Traceability updates:

| Tool | ERPNext surface | Risk | Notes |
| --- | --- | --- | --- |
| `erpnext.stock.update_batch` | `Batch` | `L4` | Requires confirmation because post-movement batch edits affect inventory traceability. |
| `erpnext.stock.update_serial_no` | `Serial No` | `L4` | Requires confirmation because post-movement serial edits affect inventory traceability. |

High-risk operation:

| Tool | ERPNext surface | Risk | Notes |
| --- | --- | --- | --- |
| `erpnext.stock.submit_document` | `Stock Entry`, `Stock Reconciliation`, `Delivery Note`, `Purchase Receipt`, `Pick List`, `Stock Reservation Entry` | `L4` | Requires explicit confirmation metadata. |

## Result Shape

Draft and master-data write tools return stable v0.2 module results instead of
raw ERPNext documents:

```json
{
  "doctype": "Stock Entry",
  "name": "MAT-STE-0001",
  "docstatus": 0,
  "status": "Draft",
  "summary": "Created Stock Entry draft with 2 item rows.",
  "next_actions": ["review_draft", "confirm_submit"],
  "risk": {
    "level": "L3",
    "requires_confirmation_for_submit": true,
    "submit_tool": "erpnext.stock.submit_document"
  }
}
```

Raw ERPNext responses are preserved under `ToolResult.debug.raw_document` for
debugging.

## Confirmation Gate

Submitting or cancelling stock-affecting documents is blocked unless
confirmation metadata is present:

```json
{
  "confirmation": {
    "confirmed_by": "warehouse.manager@example.com",
    "confirmed_at": "2026-06-09T10:00:00Z",
    "confirmation_text": "确认提交库存移动 MAT-STE-0001",
    "reason": "仓库主管已复核数量、仓库和成本影响"
  }
}
```

Guarded DocTypes:

```text
Stock Entry
Stock Reconciliation
Delivery Note
Purchase Receipt
Pick List
Stock Reservation Entry
Sales Invoice / Purchase Invoice through generic submit/cancel guard because they may affect stock and accounting
```

Blocked calls return:

```text
error_type = stock_confirmation_required
meta.risk_level = L4
```

Batch and Serial No update wrappers use the same confirmation shape and return:

```text
error_type = traceability_confirmation_required
meta.risk_level = L4
```

## PostgreSQL Catalog Integration

Stock actions must use ERPNext `Item.item_code` for final inventory operations.
When the user provides raw purchase names or informal material descriptions:

```text
erpnext.stock.resolve_item
  -> optional PostgreSQL material catalog recall
  -> ERPNext Item search
  -> selected_item_code only when ERPNext result is ready and enabled
```

If the ERPNext result is ambiguous, stock draft tools return
`item_resolution_required` and point the caller back to `erpnext.stock.resolve_item`.
The PostgreSQL `REVIEW-MAT-*` codes are search candidates only and are not used
directly in stock movements.

## Generic CRUD Boundaries

Use generic tools for simple support reads:

| Need | Preferred Tool |
| --- | --- |
| Read one known `Item` / `Item Group` / `UOM` | `erpnext.get_document` |
| Search `Item Group` or `UOM` | `erpnext.stock.list_item_groups`, `erpnext.stock.list_uoms` |
| Read stock settings or reorder policy | `erpnext.stock.get_stock_settings`, `erpnext.stock.list_item_reorders` |
| Review quality gate status | `erpnext.stock.list_quality_inspections` |
| Inspect DocType metadata | `erpnext.get_doctype_schema` |
| Attach count sheets or warehouse evidence | `erpnext.attach_file` |
| Comment on draft stock documents | `erpnext.add_comment` |

Do not use generic `erpnext.create_document` for submitted inventory changes.
Create a draft first, then submit only through a confirmed high-risk path.

## Cross-Module Boundary

Delivery Note and Purchase Receipt affect stock, but Stock tools do not own their
business creation workflow:

| DocType | Owning module | Stock module role |
| --- | --- | --- |
| `Delivery Note` | Sales | Review stock impact and ledger entries through `erpnext.stock.get_document_impact`; submit remains high-risk when used through Stock. |
| `Purchase Receipt` | Buying | Buying owns `erpnext.buying.create_purchase_receipt_draft`; Stock reviews stock impact and guards submission. |

This prevents Stock ToolCalls from silently creating sales delivery or purchasing
receiving documents while still giving warehouse users a stable way to inspect
stock effects.

## Not Implemented Yet

- Local integration smoke that creates real stock movement fixtures; safe unit coverage exists.
- Batch balance read is implemented, but FEFO batch selection and serial-number allocation helpers are still future L1 tools.

## Test Method

Unit tests:

```powershell
pytest tests/test_stock_tools.py
```

Broader tool-layer regression:

```powershell
pytest tests/test_stock_tools.py tests/test_erpnext_adapter.py
```

Optional local integration smoke, when `NEXTERP_LOCAL_*` credentials and safe
warehouse/item fixtures are available:

```powershell
pytest -m integration tests/test_erpnext_integration.py
```
