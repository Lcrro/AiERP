# ToolCall Buying Reference

Version: `tool-layer-v0.2-module-coverage`

## Scope

Buying owns procurement intent up to Purchase Receipt draft:

- Supplier
- Supplier Group
- Material Request
- Request for Quotation
- Supplier Quotation
- Purchase Order
- Purchase Receipt
- Item Supplier
- Price List / Item Price lookup
- Buying Settings
- Purchase analysis reports

Purchase Invoice, Payment Entry, and GL-impacting submission are Accounting-owned boundaries. Submitted Purchase Receipt also has stock impact, so the submit path is high risk and requires confirmation metadata.

## Implemented Tools

| Tool | Risk | Result shape | Notes |
| --- | --- | --- | --- |
| `erpnext.buying.search_suppliers` | L0 | Raw read list | Supplier lookup by name/group/type and warning/prevention flags. |
| `erpnext.buying.search_supplier_scorecards` | L0 | Module search shape | Reads Supplier Scorecard rows and RFQ/PO warn/prevent flags. |
| `erpnext.buying.get_supplier_procurement_profile` | L1 | Module preview shape | Reads Supplier, scorecards, optional Item Supplier/Item Price context, and returns RFQ/PO eligibility without creating procurement documents. |
| `erpnext.buying.create_supplier_group_draft` | L3 | Module draft shape | Master data write, no submit lifecycle. |
| `erpnext.buying.create_supplier_draft` | L3 | Module draft shape | Supplier master draft/create. |
| `erpnext.buying.create_material_request_draft` | L3 | Module draft shape | Creates draft only. |
| `erpnext.buying.create_request_for_quotation_draft` | L3 | Module draft shape | Creates RFQ draft with supplier rows. |
| `erpnext.buying.create_supplier_quotation_draft` | L3 | Module draft shape | Creates supplier quotation draft. |
| `erpnext.buying.create_purchase_order_draft` | L3 | Module draft shape | Creates PO draft only; no business commitment submit. |
| `erpnext.buying.create_purchase_receipt_draft` | L3 | Module draft shape | Creates PR draft only; no stock posting submit. |
| `erpnext.buying.generate_purchase_suggestions` | L0 | Module action shape | Uses `agent_bridge.api.generate_purchase_suggestions`. |
| `erpnext.buying.search_item_suppliers` | L0 | Raw read list | Item Supplier lookup. |
| `erpnext.buying.search_item_prices` | L0 | Raw read list | Defaults to buying Item Price rows. |
| `erpnext.buying.get_buying_settings` | L0 | Raw singleton | Reads Buying Settings. |
| `erpnext.buying.run_purchase_analysis` | L0 | Module report shape | Defaults to `Purchase Analytics`. |
| `erpnext.buying.compare_supplier_quotations` | L1 | Module preview shape | Compares Supplier Quotation totals and item rates; no award or PO creation. |
| `erpnext.buying.submit_document` | L4 | Module submit shape | Requires confirmation metadata. |

## Item Line Rule

Buying draft tools do not accept arbitrary invented `item_code` values.

Each item row must either:

- provide an ERPNext `item_code` that exists and is not disabled, or
- provide `selected_item_code` with `selection_confirmed=true`, or
- provide enough `item_query`/`specs` for `MaterialSearch` to return a ready ERPNext Item candidate.

PostgreSQL material catalog remains a search and review source. Final draft documents use ERPNext Item master data only.

If item resolution fails, the tool returns:

```json
{
  "status": "needs_item_resolution",
  "next_actions": ["search_items", "confirm_item_selection", "retry_draft_creation"],
  "risk": {"level": "L1", "requires_confirmation_for_submit": false}
}
```

## Confirmation Metadata

`erpnext.buying.submit_document` requires:

```json
{
  "confirmed_by": "buyer@example.com",
  "confirmed_at": "2026-06-09T10:00:00Z",
  "confirmation_text": "确认提交采购订单 PO-0001",
  "reason": "主管已确认供应商和价格"
}
```

Without these fields, the adapter returns `buying_confirmation_required` and does not call ERPNext.

## Generic CRUD Boundaries

Use generic tools for simple reads or uncommon Buying DocTypes when no module wrapper is needed:

- `erpnext.search_documents`
- `erpnext.get_document`
- `erpnext.get_doctype_schema`
- `erpnext.validate_fields`
- comments, assignments, and files

Do not use generic `erpnext.create_document` for procurement transaction drafts when a Buying wrapper exists, because the wrappers enforce item resolution and return stable `next_actions`.

## Supplier Quotation Comparison

`erpnext.buying.compare_supplier_quotations` is an L1 preview tool between
Supplier Quotation review and Purchase Order draft creation.

It reads the requested `Supplier Quotation` documents, ranks comparable quotes by
total amount, and returns per-item best-rate comparisons. By default, only
submitted quotations are comparable; draft quotations are listed under
`excluded_quotations` unless `include_drafts=true` is explicitly provided.

The recommendation is advisory only. The tool does not award business, send RFQ
emails, create a Purchase Order, or submit any document. After review, use
`erpnext.buying.create_purchase_order_draft` for the selected supplier and items.

## Not Yet Implemented

- Supplier scorecard write/refresh workflow. Scorecard/profile read and procurement eligibility preview are implemented.
- Automatic RFQ send/email action.
- Automatic quotation award action.
- Purchase Invoice creation; Accounting owns this boundary.
- Local ERPNext smoke creation of full Buying flow; safe unit coverage exists first.

## Tests

Unit test file:

```powershell
python -m pytest tests/test_buying_tools.py
```

Relevant assertions:

- PO draft returns v0.2 result shape.
- Buying drafts reject unconfirmed material candidates.
- Buying submit requires confirmation metadata.
- Purchase suggestions and purchase analysis expose `next_actions` and L0 risk.
- Supplier Scorecard search and Supplier procurement profile stay read-only/preview-only.
- Supplier Quotation comparison ranks totals/items without awarding business.
- Buying risk inference returns L0/L1/L3/L4 as expected.
