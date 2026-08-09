# ERPNext Tool Layer Checklist

Development version: `tool-layer-v0.1`

Scope:

```text
ToolCall
  -> ERPNext Adapter
  -> ERPNext / Frappe API
  -> ToolResult
```

This checklist tracks the backend execution layer only.

It does not include natural language understanding, Agent Runtime, role assistants, proactive reminders, or supervisor policy.

## Version Goal

`tool-layer-v0.1` should turn the current proof-of-channel into a reliable ERPNext tool layer.

The goal is not yet "every ERPNext action humans can do", but:

```text
Most common ERPNext operations can be expressed as ToolCall,
executed through the adapter,
returned as normalized ToolResult,
and tested against the local Nexterp sandbox.
```

## Current Status

Done:

- [x] `ToolCall` schema
- [x] `ToolResult` schema
- [x] ERPNext HTTP client
- [x] ERPNext adapter dispatcher
- [x] token authentication
- [x] `erpnext.get_logged_user`
- [x] `erpnext.search_documents`
- [x] `erpnext.get_document`
- [x] `erpnext.create_document`
- [x] `erpnext.update_document`
- [x] `erpnext.delete_document`
- [x] `erpnext.get_doctype_schema`
- [x] `erpnext.call_method`
- [x] `erpnext.count_documents`
- [x] `erpnext.document_exists`
- [x] `erpnext.resolve_link`
- [x] `erpnext.validate_fields`
- [x] `erpnext.submit_document`
- [x] `erpnext.cancel_document`
- [x] `erpnext.amend_document`
- [x] `erpnext.get_workflow_actions`
- [x] `erpnext.apply_workflow`
- [x] `erpnext.run_report`
- [x] `erpnext.create_todo`
- [x] `erpnext.add_comment`
- [x] `erpnext.get_comments`
- [x] `erpnext.assign_to`
- [x] `erpnext.clear_assignment`
- [x] `erpnext.attach_file`
- [x] `erpnext.list_attachments`
- [x] `erpnext.delete_attachment`
- [x] local ERPNext sandbox smoke test
- [x] `agent_bridge` app installed locally
- [x] `agent_bridge.api.ping`
- [x] `agent_bridge.api.get_low_stock_items`
- [x] `agent_bridge.api.submit_document`
- [x] `agent_bridge.api.cancel_document`
- [x] `agent_bridge.api.create_todo`

Not done:

- [x] normalized ERPNext error mapping
- [x] dedicated report tool
- [x] dedicated file attachment tool
- [x] dedicated comment tool
- [x] dedicated assignment tool
- [x] dedicated workflow tool
- [x] count/pagination support
- [x] integration tests for write operations
- [ ] remote Nexterp smoke test blocked by missing credentials

## Milestone A: Tool Protocol Hardening

Goal: make ToolCall and ToolResult reliable enough for an Agent Runtime.

- [x] Add `ToolCall.id` generation when missing.
- [x] Add `ToolCall.created_at`.
- [x] Add `ToolCall.actor` or `user_context` placeholder.
- [x] Add `ToolCall.risk_level` defaulting.
- [x] Add `ToolCall.validation_error` structure.
- [x] Add `ToolResult.tool_call_id`.
- [x] Add `ToolResult.duration_ms`.
- [x] Add `ToolResult.raw_status_code`.
- [x] Add `ToolResult.error_type`.
- [x] Add `ToolResult.user_message`.
- [x] Add tests for invalid/missing arguments.

Acceptance:

```text
Every executed ToolCall can be correlated with a ToolResult.
Every failed ToolCall returns a structured error, not only a raw exception string.
```

## Milestone B: Common Document Operations

Goal: complete the standard document operation surface.

- [x] Search documents.
- [x] Get document.
- [x] Create document.
- [x] Update document.
- [x] Delete document.
- [x] Read DocType schema.
- [x] Count documents.
- [x] Support pagination parameters.
- [x] Support ordering.
- [x] Support field aliases or safe field validation.
- [x] Add document existence check helper.
- [x] Add link-field resolution helper.
- [x] Add integration tests:
  - [x] create ToDo
  - [x] update ToDo
  - [x] get ToDo
  - [x] delete ToDo

Acceptance:

```text
The adapter can safely perform common CRUD actions on low-risk DocTypes such as ToDo.
```

## Milestone C: Document Lifecycle Tools

Goal: support ERPNext document lifecycle operations.

- [x] `agent_bridge.api.submit_document`
- [x] `agent_bridge.api.cancel_document`
- [x] Add dedicated adapter tool: `erpnext.submit_document`
- [x] Add dedicated adapter tool: `erpnext.cancel_document`
- [x] Add dedicated adapter tool: `erpnext.amend_document`
- [x] Add docstatus-aware response summaries.
- [ ] Add integration test using a safe submittable DocType. Deferred until a safe local submittable fixture is selected.

Acceptance:

```text
The Agent Runtime does not need to call generic erpnext.call_method for submit/cancel.
It can use dedicated lifecycle tools.
```

## Milestone D: Workflow Tools

Goal: support ERPNext Workflow actions.

- [x] Discover available workflow actions for a document.
- [x] Add adapter tool: `erpnext.get_workflow_actions`.
- [x] Add adapter tool: `erpnext.apply_workflow`.
- [ ] Add `agent_bridge` fallback method if Frappe API is awkward. Not needed yet; direct Frappe methods are wired.
- [ ] Add tests with a local workflow fixture or documented manual test. Deferred until a workflow fixture is selected.

Acceptance:

```text
The tool layer can list and apply workflow actions where ERPNext workflow is configured.
```

## Milestone E: Reports

Goal: let tools run ERPNext reports through a stable interface.

- [x] Research current Frappe v15 report APIs in local source.
- [x] Add adapter tool: `erpnext.run_report`.
- [x] Support report filters.
- [x] Normalize report columns and rows.
- [x] Add test against a standard report.

Acceptance:

```text
Agent can ask for report data without knowing the raw Frappe report endpoint.
```

## Milestone F: Comments, ToDo, Assignment

Goal: cover normal collaboration actions inside ERPNext.

- [x] `agent_bridge.api.create_todo`
- [x] Add dedicated adapter tool: `erpnext.create_todo`
- [x] Add adapter tool: `erpnext.add_comment`
- [x] Add adapter tool: `erpnext.get_comments`
- [x] Add adapter tool: `erpnext.assign_to`
- [x] Add adapter tool: `erpnext.clear_assignment`
- [x] Add integration tests using ToDo or Task.

Acceptance:

```text
Agent can create follow-up work and leave document-level context in ERPNext.
```

## Milestone G: Files And Attachments

Goal: support file upload and attachment to ERPNext documents.

- [x] Research Frappe upload endpoint behavior.
- [x] Add adapter tool: `erpnext.attach_file`.
- [x] Add adapter tool: `erpnext.list_attachments`.
- [x] Add adapter tool: `erpnext.delete_attachment`.
- [x] Support local file path input.
- [ ] Support content bytes/base64 input later.
- [x] Add integration test with a small text file.

Acceptance:

```text
Agent can attach a file to an ERPNext document through a ToolCall.
```

## Milestone H: Error Normalization

Goal: make ERPNext failures understandable to both Agent Runtime and users.

- [x] Map authentication errors.
- [x] Map permission errors.
- [x] Map missing DocType errors.
- [x] Map missing document errors.
- [x] Map validation errors.
- [x] Map duplicate document errors.
- [x] Map missing required field errors.
- [x] Map link validation errors.
- [x] Preserve raw error in debug metadata.
- [x] Provide short `user_message`.

Acceptance:

```text
ERPNext traceback/error payloads are normalized into stable ToolResult errors.
```

## Milestone I: agent_bridge Business Methods

Goal: add stable bridge methods for business logic that should not be guessed by the agent.

Current bridge methods:

- [x] `agent_bridge.api.ping`
- [x] `agent_bridge.api.get_low_stock_items`
- [x] `agent_bridge.api.create_todo`
- [x] `agent_bridge.api.submit_document`
- [x] `agent_bridge.api.cancel_document`

Candidate methods:

- [x] `agent_bridge.api.generate_purchase_suggestions`
- [x] `agent_bridge.api.create_material_request_draft`
- [x] `agent_bridge.api.create_sales_order_draft`
- [x] `agent_bridge.api.get_overdue_receivables_by_owner`
- [x] `agent_bridge.api.get_project_risks`
- [x] `agent_bridge.api.get_manager_exceptions`

Acceptance:

```text
Common cross-DocType business operations have bridge methods instead of fragile agent-side logic.
```

## Milestone J: Remote Nexterp Readiness

Goal: prove the same tool layer works against a real or staging Nexterp.

- [x] Add remote `.env` configuration.
- [ ] Run auth smoke test against remote. Blocked by missing credentials.
- [ ] Run read-only Customer smoke test against remote. Blocked by missing credentials.
- [ ] Run DocType schema smoke test against remote. Blocked by missing credentials.
- [ ] Confirm ERPNext/Frappe version. Blocked by missing credentials.
- [ ] Document differences from local sandbox. Blocked by missing credentials.
- [x] Do not run write tests until explicitly approved.

Acceptance:

```text
Remote Nexterp can be used through the same adapter profile without code changes.
```

## Definition Of Done For tool-layer-v0.1

`tool-layer-v0.1` is done when:

- [x] All Milestone A tasks are complete.
- [x] Milestone B CRUD tests pass.
- [x] Dedicated lifecycle tools exist.
- [x] Report, comment, ToDo, and attachment tools are implemented or explicitly deferred.
- [x] Error normalization is good enough for Agent Runtime.
- [x] Local sandbox integration tests pass when `NEXTERP_LOCAL_*` is configured.
- [x] Remote read-only smoke test is documented or blocked by missing credentials.

## Next Task

Next layer: Stage 1 Agent Runtime can now consume the dedicated tool layer.

First implementation target:

```text
natural language -> ToolCall -> tool-layer-v0.1 -> ToolResult -> natural language
```
