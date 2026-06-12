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
- Purchase Receipt Return
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
| `erpnext.buying.create_purchase_order_from_material_request_draft` | L3 | Module draft shape | Creates PO draft from a submitted Purchase Material Request and preserves MR row references. |
| `erpnext.buying.create_purchase_receipt_draft` | L3 | Module draft shape | Creates PR draft only; no stock posting submit. |
| `erpnext.buying.create_purchase_receipt_from_purchase_order_draft` | L3 | Module draft shape | Creates PR draft from a submitted Purchase Order and preserves PO row references. |
| `erpnext.buying.record_purchase_receipt_discrepancy` | L2 | Module action shape | Adds an audit comment and optional ToDo to a Purchase Receipt; can return a safe return preview, but does not create return documents or change stock. |
| `erpnext.buying.get_purchase_receipt_return_context` | L1 | Module preview shape | Reads a submitted PR and prepares returnable rows, quantities, reasons, and validation issues. |
| `erpnext.buying.create_purchase_receipt_return_draft` | L3 | Module draft shape | Creates an `is_return=1` PR return draft with `return_against` and negative item quantities; no stock posting submit. |
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

## Purchase Receipt Return

`erpnext.buying.record_purchase_receipt_discrepancy` is the first formal step
when receiving quantity, specification, quality, or package information does not
match the order. It records the discrepancy on the Purchase Receipt timeline,
optionally creates a follow-up ToDo, and can prepare return context for the
affected rows. It intentionally does not create a return draft, submit a return,
or change stock.

Use it before `erpnext.buying.create_purchase_receipt_return_draft` when the
business event is still an exception record rather than an approved return.

`erpnext.buying.get_purchase_receipt_return_context` is the safe preview step for
supplier returns after receipt. It only accepts submitted, non-return Purchase
Receipts and calculates remaining returnable quantity from each receipt item row.

`erpnext.buying.create_purchase_receipt_return_draft` creates the return draft
only when the preview has valid return rows and no quantity errors. The created
document keeps ERPNext's normal return pattern:

- `doctype = Purchase Receipt`
- `is_return = 1`
- `return_against = <original Purchase Receipt>`
- item `qty` and `received_qty` are negative

Submitting the return remains a separate `erpnext.buying.submit_document` call
with confirmation metadata, because it reverses stock impact.

## Material Request To Purchase Order

`erpnext.buying.create_purchase_order_from_material_request_draft` is the formal
wrapper for turning approved demand into a Purchase Order draft.

Rules:

- The source `Material Request` must be submitted.
- The source must be `material_request_type = Purchase`.
- Item rows keep `material_request` and `material_request_item` references.
- Item rows can keep `project` and `cost_center` context.
- Requested PO quantity cannot exceed remaining un-ordered MR quantity.
- The result is still a draft PO; submitting it is a separate confirmed
  `erpnext.buying.submit_document` action.

## Purchase Order To Purchase Receipt

`erpnext.buying.create_purchase_receipt_from_purchase_order_draft` is the formal
wrapper for turning an approved Purchase Order into a receiving draft.

Rules:

- The source `Purchase Order` must be submitted.
- Item rows keep `purchase_order` and `purchase_order_item` references.
- Item rows can keep `project` and `cost_center` context.
- Requested receipt quantity cannot exceed remaining unreceived PO quantity.
- The result is still a draft PR; submitting it is a separate confirmed
  `erpnext.buying.submit_document` action because it posts stock impact.

## Not Yet Implemented

- Supplier scorecard write/refresh workflow. Scorecard/profile read and procurement eligibility preview are implemented.
- Automatic RFQ send/email action.
- Automatic quotation award action.
- Purchase Invoice creation remains Accounting-owned; the PR -> PI source-document wrapper is implemented in Accounting.
- Full stateful scenario runner smoke is still pending, although MR -> submitted MR -> PO -> submitted PO -> PR -> submitted PR -> PI local smoke has passed in targeted scripts.

## Tests

Unit test file:

```powershell
python -m pytest tests\unit\erpnext\test_buying_tools.py -q
```

Relevant assertions:

- PO draft returns v0.2 result shape.
- MR item rows preserve project/cost-center context.
- Submitted MR can generate PO draft with source row references.
- Draft MR cannot generate PO draft.
- Submitted PO can generate PR draft with source row references.
- Draft PO cannot generate PR draft.
- Buying drafts reject unconfirmed material candidates.
- Buying submit requires confirmation metadata.
- Purchase suggestions and purchase analysis expose `next_actions` and L0 risk.
- Supplier Scorecard search and Supplier procurement profile stay read-only/preview-only.
- Supplier Quotation comparison ranks totals/items without awarding business.
- Purchase Receipt discrepancy records a comment and ToDo, and returns a safe return preview without changing stock.
- Purchase Receipt return preview and return draft creation use submitted originals and negative quantities.
- Local ERPNext smoke verified `MAT-MR-2026-00005 -> PUR-ORD-2026-00024`, preserving `material_request`, `material_request_item`, and `project` on the PO row.
- Local ERPNext smoke verified `MAT-MR-2026-00006 -> PUR-ORD-2026-00025 -> MAT-PRE-2026-00007`, preserving `purchase_order`, `purchase_order_item`, and `project` on the PR row.
- Local ERPNext smoke verified `erpnext.buying.record_purchase_receipt_discrepancy` on `MAT-PRE-2026-00007`, creating a comment, a ToDo, and one return-preview row.
- Buying risk inference returns L0/L1/L2/L3/L4 as expected.
