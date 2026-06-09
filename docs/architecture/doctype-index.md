# DocType Index And Agent Context

This document defines how Nexterp Agent should understand ERPNext/Nexterp DocTypes.

The purpose of this layer is simple:

```text
Do not let the agent guess ERPNext structure.
Read ERPNext metadata, summarize it, cache it, and give the relevant parts to the agent before it creates ToolCalls.
```

ERPNext already knows its schema. The agent layer should use that truth instead of relying on memory, hardcoded examples, or fragile prompt guesses.

## Architecture Position

The DocType index belongs between ERPNext metadata and Agent Runtime.

```text
ERPNext / Frappe metadata
  -> DocType Indexer
  -> local JSON cache
  -> DocType Context Retriever
  -> Agent Runtime
  -> ToolCall generation
```

It supports Stage 1 by making ToolCall generation more accurate.

It becomes essential in later stages when employees ask the agent to create, update, submit, or inspect many different ERPNext documents.

## Current Verified State

Local sandbox:

```text
/home/administrator/frappe-bench
```

Installed apps:

```text
frappe 15.107.5
erpnext 15.108.1
frappe_assistant_core 2.4.3
agent_bridge 0.0.1
```

Local ERPNext URL:

```text
http://localhost:8001
```

Current adapter capabilities:

- authenticate with ERPNext API token
- call `/api/method/frappe.auth.get_logged_user`
- query documents with `/api/resource/{doctype}`
- read DocType schema with `/api/v2/doctype/{doctype}/meta`
- call whitelisted methods with `/api/method/{method}`
- call `agent_bridge.api.ping`

Current local bridge app:

```text
/home/administrator/frappe-bench/apps/agent_bridge
```

Tracked bridge mirror:

```text
frappe_apps/agent_bridge/
```

## Lesson Already Learned

Field assumptions are dangerous.

Real example from implementation:

```text
Initial assumption:
tabBin has reorder_level

Actual ERPNext v15 schema:
tabBin does not have reorder_level

Correct location:
tabItem Reorder
  - warehouse_reorder_level
  - warehouse_reorder_qty
  - material_request_type
```

This is the exact class of mistake the DocType index must prevent.

## Goals

The DocType index must support these actions:

```text
Scan all DocTypes
Read fields, permissions, child tables, and submit status
Detect required fields
Detect link fields and table fields
Generate compact DocType summaries
Cache summaries as local JSON
Retrieve relevant summaries for Agent Runtime
Help the agent produce valid ToolCalls
Help the agent ask follow-up questions instead of guessing
```

## Non-Goals

The first version should not try to:

- replace ERPNext permissions
- store live business data such as orders, inventory, invoices, or customer balances
- expose all DocType metadata to every user
- teach the agent every business process
- solve policy approval or supervision
- infer custom business meaning without source metadata or examples

Live business data must still be fetched from ERPNext at execution time.

The DocType index is structural knowledge, not operational data.

## Data Sources

### Primary Metadata API

Preferred:

```text
GET /api/v2/doctype/{doctype}/meta
```

This returns DocType metadata including fields, permissions, actions, links, and states in Frappe v15.

### Fallback Metadata Method

Fallback:

```text
POST /api/method/frappe.desk.form.load.getdoctype
```

Arguments:

```json
{
  "doctype": "Customer",
  "with_parent": 1
}
```

### Listing DocTypes

Preferred first implementation:

```text
erpnext.search_documents
doctype: "DocType"
fields: ["name", "module", "istable", "issingle", "is_submittable", "custom", "modified"]
```

Fallback:

```text
GET /api/resource/DocType
```

### Debugging Sources

Useful bench commands:

```bash
cd ~/frappe-bench
bench --site localhost list-apps
bench --site localhost mariadb -e "desc tabBin;"
bench --site localhost mariadb -e "desc \`tabItem Reorder\`;"
bench --site localhost mariadb -e "select name,module,istable,is_submittable from tabDocType limit 20;"
```

Useful source locations:

```text
/home/administrator/frappe-bench/apps/frappe
/home/administrator/frappe-bench/apps/erpnext
/home/administrator/frappe-bench/apps/agent_bridge
```

## Indexer Components

Target code layout:

```text
src/nexterp_agent/doctype_index/
  __init__.py
  indexer.py              # scans ERPNext and writes cache
  extractor.py            # converts raw metadata to compact summaries
  cache.py                # reads/writes JSON cache
  retriever.py            # selects relevant summaries for Agent Runtime
  models.py               # typed summary objects

scripts/
  index_doctypes.py       # CLI for generating index
  inspect_doctype.py      # CLI for debugging one DocType
```

The indexer should use the existing `ERPNextAdapter` and `ERPNextClient`.

It should not introduce another ERPNext HTTP client.

## Cache Layout

Default cache directory:

```text
.cache/doctype_index/
```

The cache should not be committed.

Recommended files:

```text
.cache/doctype_index/manifest.json
.cache/doctype_index/all_doctypes.json
.cache/doctype_index/doctype_summaries.json
.cache/doctype_index/role_doctype_map.json
.cache/doctype_index/modules.json
.cache/doctype_index/doctypes/Customer.json
.cache/doctype_index/doctypes/Sales Order.json
.cache/doctype_index/doctypes/Purchase Order.json
```

### Manifest

`manifest.json` should describe the cache itself:

```json
{
  "schema_version": 1,
  "profile": "local",
  "base_url": "http://localhost:8001",
  "site": "localhost",
  "generated_at": "2026-06-08T17:30:00+08:00",
  "frappe_version": "15.107.5",
  "erpnext_version": "15.108.1",
  "doctype_count": 742,
  "submittable_count": 83,
  "child_table_count": 214
}
```

Do not store API keys or secrets in the manifest.

## DocType Summary Model

Each indexed DocType should produce one compact summary.

```json
{
  "doctype": "Sales Order",
  "module": "Selling",
  "description": "Sales transaction document...",
  "is_single": false,
  "is_virtual": false,
  "is_tree": false,
  "is_child_table": false,
  "is_submittable": true,
  "custom": false,
  "title_field": "customer",
  "search_fields": ["customer", "transaction_date"],
  "sort_field": "modified",
  "sort_order": "DESC",
  "fields": [],
  "required_fields": [],
  "link_fields": [],
  "table_fields": [],
  "list_fields": [],
  "standard_filter_fields": [],
  "permissions": [],
  "actions": [],
  "states": [],
  "links": [],
  "child_tables": [],
  "common_operations": [],
  "agent_notes": []
}
```

### Field Summary Model

Each field summary should keep only the details useful to tool planning.

```json
{
  "fieldname": "customer",
  "label": "Customer",
  "fieldtype": "Link",
  "options": "Customer",
  "required": true,
  "read_only": false,
  "hidden": false,
  "set_only_once": false,
  "allow_on_submit": false,
  "in_list_view": true,
  "in_standard_filter": true,
  "search_index": true,
  "default": null,
  "depends_on": null,
  "mandatory_depends_on": null,
  "read_only_depends_on": null,
  "permlevel": 0
}
```

Important field types:

```text
Data
Int
Float
Currency
Check
Date
Datetime
Select
Link
Dynamic Link
Table
Table MultiSelect
Text
Small Text
Long Text
Code
Attach
Attach Image
Section Break
Column Break
Tab Break
```

For Agent Runtime, layout fields such as `Section Break`, `Column Break`, and `Tab Break` should usually be excluded from required-field reasoning.

### Link Field Model

```json
{
  "fieldname": "customer",
  "label": "Customer",
  "target_doctype": "Customer",
  "required": true
}
```

For `Dynamic Link`, include the controlling field:

```json
{
  "fieldname": "party",
  "label": "Party",
  "target_doctype": null,
  "dynamic_target_field": "party_type",
  "required": true
}
```

### Table Field Model

```json
{
  "fieldname": "items",
  "label": "Items",
  "child_doctype": "Sales Order Item",
  "required": true
}
```

The indexer should also index the child DocType itself.

### Permission Summary Model

```json
{
  "role": "Sales User",
  "permlevel": 0,
  "read": true,
  "write": true,
  "create": true,
  "submit": false,
  "cancel": false,
  "delete": false,
  "amend": false,
  "report": true,
  "export": false,
  "import": false,
  "share": true,
  "print": true,
  "email": true,
  "if_owner": false
}
```

The index is not a permission enforcement layer.

It helps the agent understand likely ability, but ERPNext remains the source of truth.

## Extraction Rules

### Required Fields

A field is required when:

```text
field.reqd == 1
```

Also record conditional requirements:

```text
mandatory_depends_on
```

Agent behavior:

```text
If required write fields are missing, ask a follow-up question.
Do not invent values unless the field has a safe default.
```

### Hidden And Read-Only Fields

Hidden fields should normally be excluded from user-facing prompts.

Read-only fields should normally not be included in create/update ToolCalls unless ERPNext explicitly expects them through a server-side process.

### Submit Status

Submittable DocTypes matter because they usually have lifecycle states:

```text
Draft -> Submitted -> Cancelled
```

Agent behavior:

```text
Create as draft first.
Submit only when the user explicitly asks or a later policy layer approves.
```

### Child Tables

For document creation, child tables are often the most important part.

Example:

```text
Sales Order
  items -> Sales Order Item
```

Agent behavior:

```text
When creating a parent document with required table fields,
load both parent and child summaries before generating ToolCall.
```

### Link Fields

For Link fields, the agent should verify referenced documents exist.

Example:

```text
customer -> Customer
item_code -> Item
supplier -> Supplier
```

Agent behavior:

```text
Before creating or updating a document with Link fields,
use search/get tools to resolve ambiguous names.
```

## Role Context Retrieval

Do not inject every DocType into every prompt.

Instead:

```text
user role + user message + recent context
  -> likely business area
  -> relevant DocType summaries
  -> Agent Runtime prompt/tool context
```

### Initial Role-To-DocType Map

Purchase:

```text
Supplier
Item
Bin
Item Reorder
Material Request
Material Request Item
Purchase Order
Purchase Order Item
Purchase Receipt
Supplier Quotation
ToDo
```

Sales:

```text
Customer
Lead
Opportunity
Quotation
Quotation Item
Sales Order
Sales Order Item
Delivery Note
Sales Invoice
ToDo
```

Warehouse:

```text
Item
Bin
Warehouse
Stock Entry
Stock Entry Detail
Delivery Note
Purchase Receipt
Batch
Serial No
ToDo
```

Finance:

```text
Customer
Supplier
Sales Invoice
Purchase Invoice
Payment Entry
Journal Entry
Account
GL Entry
ToDo
```

Technician:

```text
Task
Issue
Project
Work Order
Job Card
Maintenance Visit
Maintenance Schedule
ToDo
```

Project Manager:

```text
Project
Task
Timesheet
Issue
Milestone
ToDo
```

Company Manager:

```text
Sales Order
Purchase Order
Sales Invoice
Purchase Invoice
Payment Entry
Project
Task
Issue
Bin
ToDo
```

General Employee:

```text
ToDo
Task
File
Comment
User
Employee
```

This map is only the starting point. It should be refined from actual Nexterp usage.

## Agent Runtime Usage

When the user says:

```text
帮我创建一个采购申请
```

The agent should:

```text
1. Load role context: Purchase
2. Retrieve summaries:
   - Material Request
   - Material Request Item
   - Item
   - Warehouse
   - Supplier if relevant
3. Check required fields
4. Ask follow-up questions for missing values
5. Resolve Link fields through ERPNext search tools
6. Generate ToolCall for erpnext.create_document
7. Let ERPNext validate
8. Explain success or validation error
```

When the user says:

```text
帮我整理低于安全库存的物料
```

The agent should prefer the bridge method if available:

```json
{
  "tool": "erpnext.call_method",
  "arguments": {
    "method": "agent_bridge.api.get_low_stock_items",
    "args": {
      "limit": 50
    }
  }
}
```

Why:

```text
Low-stock logic spans Bin + Item Reorder.
A bridge method is safer than forcing the agent to compose SQL-like business logic from generic tools.
```

## Generic Tools Versus agent_bridge

Use generic adapter tools when the operation maps cleanly to DocType CRUD:

```text
erpnext.search_documents
erpnext.get_document
erpnext.create_document
erpnext.update_document
erpnext.delete_document
erpnext.get_doctype_schema
```

Use `agent_bridge` when:

- the logic spans multiple DocTypes
- ERPNext UI button behavior is hard to reproduce through generic REST
- validation or defaults should be handled server-side
- the operation is a common business workflow
- the agent would otherwise need too much internal ERPNext knowledge

Candidate bridge methods:

```text
agent_bridge.api.get_low_stock_items
agent_bridge.api.create_sales_order_draft
agent_bridge.api.generate_purchase_suggestions
agent_bridge.api.get_overdue_receivables_by_owner
agent_bridge.api.get_project_risks
agent_bridge.api.get_manager_exceptions
```

## Indexing Algorithm

First version:

```text
1. Load ERPNext settings by profile
2. Build ERPNextAdapter
3. Fetch DocType list
4. For each DocType:
   4.1 Fetch metadata
   4.2 Extract compact summary
   4.3 Write per-DocType JSON
5. Write aggregate summary files
6. Write manifest
7. Print stats
```

For development, support an allowlist:

```powershell
python scripts/index_doctypes.py --profile local --only Customer Item Bin "Item Reorder" ToDo
```

Full scan:

```powershell
python scripts/index_doctypes.py --profile local --all
```

Inspect one DocType:

```powershell
python scripts/inspect_doctype.py --profile local "Sales Order"
```

## Refresh Strategy

Initial refresh:

```text
manual CLI command
```

Later refresh:

```text
on app start if cache missing
scheduled daily refresh
manual refresh after ERPNext customization
manual refresh after migration/update
```

The indexer should compare `modified` timestamps from `DocType` records where possible.

Avoid refreshing every turn.

## Cache Safety

The cache may include custom company-specific schema.

Default rule:

```text
Do not commit .cache/doctype_index/
```

The cache should not include:

- API keys
- API secrets
- user passwords
- session IDs
- live customer balances
- live inventory quantities
- invoice data
- order data

The cache may include:

- DocType names
- field names
- labels
- field types
- permission rows
- child table mappings
- link mappings
- module names

## Error Handling

Indexer should keep going when one DocType fails.

For each failed DocType, record:

```json
{
  "doctype": "Some DocType",
  "ok": false,
  "error": "PermissionError or API error",
  "stage": "fetch_meta"
}
```

Final output should include:

```text
Indexed: 730
Failed: 12
Skipped: 0
```

Agent Runtime should treat missing summaries as recoverable:

```text
If cache missing, call erpnext.get_doctype_schema live.
If live schema fails, ask user for clarification or report limitation.
```

## Testing Plan

Unit tests:

- extract required fields from raw metadata
- extract link fields
- extract table fields
- exclude layout-only fields from prompts
- write/read cache files

Integration tests against local sandbox:

- index `Customer`
- index `Item`
- index `Bin`
- index `Item Reorder`
- index `Sales Order`
- index `Purchase Order`
- index `Material Request`
- index `ToDo`

Smoke command:

```powershell
python scripts/index_doctypes.py --profile local --only Customer Item Bin "Item Reorder" ToDo
```

## Stage 1 MVP

For the first implementation, index only this allowlist:

```text
Customer
Supplier
Item
Bin
Item Reorder
Sales Order
Sales Order Item
Purchase Order
Purchase Order Item
Material Request
Material Request Item
Task
Issue
Project
ToDo
```

This is enough to support early natural language experiments across:

- sales
- purchase
- warehouse
- technician
- project manager
- general employee

## Stage 2 Expansion

After the MVP works:

- scan all DocTypes
- add role-to-DocType retrieval
- add report registry
- add whitelisted method registry where discoverable
- add workflow metadata
- add custom DocType grouping
- add LLM-generated business summaries if deterministic summaries are not enough

## Open Questions

- How should custom Nexterp DocTypes be grouped by business area?
- Should role-to-DocType mapping be configured manually, inferred, or both?
- Should generated summaries be deterministic only, or enhanced by an LLM?
- Should the cache be per environment, per site, per company, or per user role?
- How often should the index refresh in production?
- Which metadata is safe to show to each employee role?
- Should the supervisor layer later review schema context shown to the agent?

## Immediate Next Step

Implement:

```text
scripts/index_doctypes.py
```

Minimum implementation:

```text
1. Accept --profile local
2. Accept --only list of DocTypes
3. Fetch metadata through ERPNextAdapter
4. Extract compact summaries
5. Write .cache/doctype_index/
6. Print stats
7. Add unit tests for extractor
```
