# ERPNext Tool Layer v0.2 Module Coverage

Development version: `tool-layer-v0.2-module-coverage`

## Goal

Upgrade the current generic ERPNext tool layer into module-aware ToolCall coverage for:

- Users & Permissions
- Assets
- Stock
- Buying
- Accounting

The target is not merely to expose raw CRUD for these modules. The target is:

```text
employee business intent
  -> stable module ToolCall
  -> ERPNext Adapter or agent_bridge wrapper
  -> ERPNext/Frappe validation
  -> normalized ToolResult with risk and audit context
```

## Current Baseline

Already available from `tool-layer-v0.1`:

- generic document search/get/create/update/delete
- count, pagination, ordering
- link resolution and field validation
- DocType schema reading
- submit/cancel/amend
- workflow actions
- report execution
- ToDo, comments, assignment
- file attachment
- material master/search foundation

These generic tools remain the fallback for simple actions. v0.2 adds module tools where raw CRUD is too ambiguous, risky, or business-specific.

## Tool Naming

Use module-specific names when a business action has meaning beyond raw document CRUD:

| Module | Tool Prefix | Examples |
| --- | --- | --- |
| Users & Permissions | `erpnext.users.*` | `erpnext.users.list_users`, `erpnext.users.create_user_draft`, `erpnext.users.assign_roles` |
| Assets | `erpnext.assets.*` | `erpnext.assets.create_asset_draft`, `erpnext.assets.create_movement_draft` |
| Stock | `erpnext.stock.*` | `erpnext.stock.get_balance`, `erpnext.stock.create_entry_draft` |
| Buying | `erpnext.buying.*` | `erpnext.buying.create_material_request_draft`, `erpnext.buying.create_purchase_order_draft` |
| Accounting | `erpnext.accounting.*` | `erpnext.accounting.get_receivables`, `erpnext.accounting.create_payment_entry_draft` |

Use the existing generic tools for:

- simple read of a known DocType
- safe low-risk draft creation when no business wrapper is needed
- comments, files, assignments, workflow, reports

Do not add a dedicated tool that only renames `erpnext.create_document` unless it adds validation, defaults, risk metadata, clearer result shape, or safer business semantics.

## Risk Levels

Keep `ToolCall.risk_level` simple but explicit:

| Level | Meaning | Examples |
| --- | --- | --- |
| `L0` | Read-only, no business state change | search, get, count, report |
| `L1` | Low-impact helper or metadata operation | validation, preview, prepare |
| `L2` | Collaboration or reversible low-risk write | comment, ToDo, assignment |
| `L3` | Draft business document or master data write | draft PO, draft stock entry, draft asset |
| `L4` | Submitted operational change | submit stock entry, submit purchase order |
| `L5_ADMIN` | Permission, user, role, or system setting change | assign role, create user, set user permission |
| `L5_FINANCIAL` | Financial posting, payment, invoice, GL-impacting action | submit payment, submit journal entry |

Module tools should either set their own risk explicitly in documentation and schemas or be added to `infer_risk_level`.

## Confirmation Metadata

High-risk tools should accept optional confirmation metadata even before the supervisor/policy layer exists:

```json
{
  "confirmation": {
    "confirmed_by": "user@example.com",
    "confirmed_at": "2026-06-09T10:00:00Z",
    "confirmation_text": "确认提交采购订单 PO-0001",
    "reason": "主管已确认供应商和价格"
  }
}
```

The adapter should not silently execute `L4`, `L5_ADMIN`, or `L5_FINANCIAL` module actions that perform irreversible or externally meaningful changes unless the tool is explicitly documented as draft-only or read-only.

For v0.2, it is acceptable to implement high-risk actions as draft creation plus documentation of the required submit path.

## Result Shape

Module tools should return stable `ToolResult.data` structures:

```json
{
  "doctype": "Purchase Order",
  "name": "PO-0001",
  "docstatus": 0,
  "status": "Draft",
  "summary": "Created purchase order draft for Supplier A with 3 items.",
  "next_actions": ["review_prices", "confirm_submit"],
  "risk": {
    "level": "L3",
    "requires_confirmation_for_submit": true
  }
}
```

Avoid returning raw ERPNext documents only. Raw documents may be included under `debug` if needed.

## Module Acceptance Criteria

Each module owner should deliver:

1. Module capability map:
   - core DocTypes
   - common employee actions
   - tools implemented
   - tools intentionally left to generic CRUD
   - actions needing `agent_bridge`
   - risk classification
2. Tool schemas in `tool_registry.py`.
3. Adapter handlers and client/bridge methods as needed.
4. Unit tests for dispatch, argument validation, and result shape.
5. Local integration smoke where safe.
6. Reference document under `docs/reference/toolcall-<module>.md`.

## Module Boundaries

### Users & Permissions

Scope:

- User
- Role
- Role Profile
- User Permission
- document sharing
- activity/access logs
- permission-related metadata

High-risk:

- creating users
- disabling users
- assigning roles
- changing user permissions
- changing DocPerm/Custom DocPerm

### Assets

Scope:

- Asset
- Asset Category
- Asset Location
- Asset Movement
- Asset Maintenance
- Asset Repair
- value adjustment and depreciation support

High-risk:

- capitalization
- depreciation posting
- value adjustment
- disposal/sale

### Stock

Scope:

- Item and Item Group integration
- Warehouse
- Bin and stock balance
- Stock Entry
- Stock Reconciliation
- Batch
- Serial No
- Stock Ledger Entry read-only analysis

High-risk:

- submitted stock movement
- stock reconciliation
- batch/serial changes after movement

### Buying

Scope:

- Supplier
- Material Request
- Request for Quotation
- Supplier Quotation
- Purchase Order
- Purchase Receipt
- Item Supplier and price lookup

High-risk:

- submitted purchase orders
- purchase receipts
- purchase invoices only as Accounting-owned or shared boundary

### Accounting

Scope:

- Account
- Cost Center
- Journal Entry
- Payment Entry
- Sales Invoice and Purchase Invoice accounting side
- GL Entry read-only
- receivable/payable reports
- bank and tax structures
- budget/fiscal periods

High-risk:

- payment submission
- journal entry submission
- invoice submission
- period close
- tax and account structure changes

## Integration Rule

If two modules touch the same DocType:

- Buying owns purchase business intent up to Purchase Receipt draft.
- Accounting owns Purchase Invoice, Payment Entry, GL-impacting submit actions.
- Stock owns inventory movement and stock ledger effects.
- Assets owns fixed asset lifecycle.
- Users & Permissions owns access changes.

When in doubt, implement a draft/preparation tool and document the boundary instead of creating a hidden cross-module side effect.

## Verification Loop

Main thread will:

1. Review each subagent's changed files.
2. Run module unit tests.
3. Run safe local ERPNext smoke tests when available.
4. Check that risk levels and confirmation expectations are present.
5. Send concrete follow-up instructions to subagents until the module is good enough.

The goal is long-running. A module is not "complete" merely because a few tools exist; it is complete only when the common module workflows are covered, documented, and verified.

## Current Verification Status

Last checked on 2026-06-09:

- Module tool schemas exist for Users & Permissions, Assets, Stock, Buying, and Accounting.
- Adapter handlers exist for all registered tool schemas: `137` tool schemas, `137` handlers, `missing=[]`, `extra=[]`.
- Module schema counts: Users & Permissions `18`, Stock `35`, Buying `17`, Accounting `24`, Assets `13`.
- Reference docs exist for all five priority modules.
- High-risk module submit/admin/financial actions require confirmation metadata.
- Users & Permissions now includes `erpnext.users.preview_permission_policy_change` for preview-only DocPerm-style before/after/diff simulation; actual DocPerm/Custom DocPerm writes remain intentionally unimplemented.
- Latest low-risk module additions: Buying supplier scorecard/profile preview, Stock batch balances, Assets depreciation schedule read, and Accounting report filter contract read.
- Five priority module unit tests pass: `60 passed`.
- Full test suite without local credentials passes with local integration skipped: `97 passed, 3 skipped`.
- Full test suite with local `.env` loaded passes against the sandbox: `100 passed`.

Current status is module-aware ToolCall foundation, not final full ERPNext parity. Recent additions include server-side permission check wiring, stock settings/reorder/quality reads, supplier quotation comparison, accounting reference reads plus generic financial write guards, and asset financial snapshots. Remaining work should focus on safe local ERPNext smoke tests, more verified `agent_bridge` wrappers for ERPNext UI button flows, and deeper workflow coverage for the gaps listed in each module reference doc.
