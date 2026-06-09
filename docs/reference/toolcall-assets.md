# ERPNext Assets ToolCalls

This document tracks v0.2 module-aware ToolCall coverage for ERPNext Assets.

## Scope

Core DocTypes:

| Area | DocTypes |
| --- | --- |
| Asset master | Asset, Asset Category, Asset Location |
| Lifecycle movement | Asset Movement |
| Maintenance | Asset Maintenance, Asset Maintenance Log |
| Repair | Asset Repair |
| Valuation | Asset Value Adjustment, depreciation-related Asset fields/schedules |
| Financial boundary | Journal Entry, Sales Invoice, Purchase Invoice, GL Entry are Accounting-owned |

## Implemented Tools

| Tool | Risk | Action |
| --- | --- | --- |
| `erpnext.assets.search_assets` | L0 | Search Asset rows with stable default fields. |
| `erpnext.assets.search_asset_categories` | L0 | Search Asset Category master records. |
| `erpnext.assets.search_asset_locations` | L0 | Search Asset Location records. |
| `erpnext.assets.get_financial_snapshot` | L0 | Read one Asset's financial/depreciation context and optional depreciation schedules; no GL, sale, disposal, or depreciation posting. |
| `erpnext.assets.get_depreciation_schedule` | L0 | Reads Asset Depreciation Schedule records and optional due schedule rows; does not post depreciation. |
| `erpnext.assets.create_asset_draft` | L3 | Create Asset draft with `docstatus=0`; capitalization submit is separate. |
| `erpnext.assets.create_movement_draft` | L3 | Create Asset Movement draft for issue/receipt/transfer. |
| `erpnext.assets.create_maintenance_draft` | L3 | Create Asset Maintenance plan draft. |
| `erpnext.assets.create_maintenance_log_draft` | L3 | Create Asset Maintenance Log draft. |
| `erpnext.assets.create_repair_draft` | L3 | Create Asset Repair draft. |
| `erpnext.assets.create_value_adjustment_draft` | L3 | Create Asset Value Adjustment draft; submit is financial high risk. |
| `erpnext.assets.prepare_disposal_or_sale` | L1 | Read-only preparation for disposal/scrap/sale; does not post GL or create invoice. |
| `erpnext.assets.submit_document` | L4 or L5_FINANCIAL | Submit supported asset lifecycle documents after confirmation metadata. |

All draft tools return normalized `ToolResult.data` with:

- `doctype`
- `name`
- `docstatus`
- `status`
- `summary`
- `next_actions`
- `risk`

## Confirmation Rules

High-risk asset actions require:

```json
{
  "confirmation": {
    "confirmed_by": "asset.manager@example.com",
    "confirmed_at": "2026-06-09T10:00:00Z",
    "confirmation_text": "Confirm asset capitalization AST-0001",
    "reason": "Manager approved fixed asset capitalization"
  }
}
```

Guarded paths:

| Path | Guard |
| --- | --- |
| `erpnext.assets.submit_document` for Asset or Asset Value Adjustment | `L5_FINANCIAL` confirmation required |
| `erpnext.assets.submit_document` for movement/maintenance/log/repair | `L4` confirmation required |
| generic `erpnext.submit_document` / `erpnext.cancel_document` for asset DocTypes | same asset confirmation guard |
| `erpnext.call_method` to `agent_bridge.api.submit_document` / `cancel_document` for asset DocTypes | same asset confirmation guard |

## Generic Tool Coverage

Use generic tools instead of dedicated Assets tools for:

| Need | Tool |
| --- | --- |
| Read a known Asset or Asset Movement by name | `erpnext.get_document` |
| Review asset financial/depreciation context | `erpnext.assets.get_financial_snapshot` |
| Inspect live fields/customizations | `erpnext.get_doctype_schema` |
| Validate user-provided field names | `erpnext.validate_fields` |
| Attach invoices, photos, or maintenance evidence | `erpnext.attach_file`, `erpnext.list_attachments` |
| Comments, follow-ups, assignments | `erpnext.add_comment`, `erpnext.create_todo`, `erpnext.assign_to` |
| Reports not wrapped by Assets | `erpnext.run_report` |

## Boundaries And Gaps

Not implemented as direct posting tools:

| Workflow | Status |
| --- | --- |
| Depreciation posting | Accounting/ERPNext scheduler and GL-impacting entries; use reports or Accounting-owned draft/posting tools. |
| Depreciation schedule review | Supported read-only by `erpnext.assets.get_financial_snapshot` and `erpnext.assets.get_depreciation_schedule`; posting remains out of scope. |
| Asset sale invoice creation | Accounting/Sales boundary. `prepare_disposal_or_sale` returns next actions but does not create invoice. |
| Asset scrapping/disposal posting | Financial high risk. Current tool prepares and documents the required handoff. |
| ERPNext UI button wrappers such as make invoice or process depreciation | Deferred until local method names are verified in ERPNext source or agent_bridge. |

## Test Coverage

Unit tests:

```powershell
pytest tests/test_assets_tools.py
```

Covered:

- read-only dispatch and normalized result shape
- asset financial snapshot shape, depreciation schedule expansion/filtering, and L0 risk inference
- draft creation forces `docstatus=0`
- disposal/sale preparation is read-only and marked financial high risk
- `erpnext.assets.submit_document` blocks without confirmation
- generic `erpnext.submit_document` blocks Asset submit without confirmation
- risk-level inference for Assets tools

Safe local smoke:

1. `erpnext.assets.search_asset_categories`
2. `erpnext.assets.search_asset_locations`
3. `erpnext.assets.search_assets` with small `limit`
4. Draft creation only in a sandbox company
5. Do not submit Asset, Asset Value Adjustment, disposal, sale, or depreciation postings without explicit business approval.
