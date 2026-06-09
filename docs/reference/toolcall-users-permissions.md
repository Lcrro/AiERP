# Users & Permissions ToolCall Coverage

Development scope: `tool-layer-v0.2-module-coverage`

Tool prefix: `erpnext.users.*`

## Core DocTypes

| Area | DocTypes |
| --- | --- |
| Users | `User`, child table `Has Role` |
| Roles | `Role`, `Role Profile` |
| User restrictions | `User Permission` |
| Sharing | `DocShare` |
| Permission metadata | DocType metadata `permissions`, `DocPerm`, `Custom DocPerm` |
| Audit logs | `Access Log`, `Activity Log` |

## Implemented Tools

| Tool | Risk | Behavior |
| --- | --- | --- |
| `erpnext.users.list_users` | `L0` | Lists users with identity, enabled status, type, role profile, and login timestamps. |
| `erpnext.users.get_user_access_summary` | `L0` | Reads one user, roles, role profile, enabled status, and direct `User Permission` rows. |
| `erpnext.users.list_roles` | `L0` | Lists roles with desk access and disabled flags. |
| `erpnext.users.list_role_profiles` | `L0` | Lists role profiles. |
| `erpnext.users.preview_role_profile_roles` | `L0` | Expands one Role Profile into its role list before user creation or role assignment. |
| `erpnext.users.list_user_permissions` | `L0` | Lists `User Permission` rows by user, allowed DocType, value, or applicable DocType. |
| `erpnext.users.list_shared_documents` | `L0` | Lists `DocShare` rows for a user or shared document. |
| `erpnext.users.list_access_logs` | `L0` | Lists `Access Log` rows for audit review. |
| `erpnext.users.list_activity_logs` | `L0` | Lists `Activity Log` rows for audit review. |
| `erpnext.users.get_permission_metadata` | `L0` | Reads DocType permission metadata without changing `DocPerm` or `Custom DocPerm`. |
| `erpnext.users.preview_effective_permissions` | `L0` | Previews a user's likely permissions on one DocType from metadata roles plus direct `User Permission` rows; not exact runtime evaluation. |
| `erpnext.users.check_server_permission` | `L0` | Calls `agent_bridge.api.check_user_permission` for server-side Frappe permission evaluation by user, DocType, action, and optional document name. |
| `erpnext.users.preview_permission_policy_change` | `L5_ADMIN` | Preview-only tool that simulates DocPerm-style add/update/remove changes and returns before/after/diff without writing ERPNext. |
| `erpnext.users.create_user_draft` | `L5_ADMIN` | Creates a User record with `enabled=0` and welcome email disabled by default, only after explicit confirmation. |
| `erpnext.users.set_user_enabled` | `L5_ADMIN` | Enables or disables a user, only after explicit confirmation. |
| `erpnext.users.assign_roles` | `L5_ADMIN` | Replaces, adds, or removes `Has Role` rows on a user, only after explicit confirmation. |
| `erpnext.users.create_user_permission` | `L5_ADMIN` | Creates a `User Permission` row, only after explicit confirmation. |
| `erpnext.users.delete_user_permission` | `L5_ADMIN` | Deletes a `User Permission` row by name, only after explicit confirmation. |

## Confirmation Contract

All `L5_ADMIN` write tools require:

```json
{
  "confirmation": {
    "confirmed": true,
    "confirmed_by": "admin@example.com",
    "confirmed_at": "2026-06-09T10:00:00Z",
    "confirmation_text": "确认执行权限变更",
    "reason": "权限负责人已批准"
  }
}
```

If confirmation is missing, the adapter returns:

- `ok=false`
- `error_type=admin_confirmation_required`
- `meta.risk_level=L5_ADMIN`
- `data.preview` containing the pending change
- no ERPNext write call is made

This keeps the adapter audit-friendly before the later supervisor/policy layer exists.

## Result Shape

Read tools return:

```json
{
  "doctype": "User",
  "status": "Read Only",
  "summary": "Listed ERPNext users.",
  "records": [],
  "next_actions": ["review_results", "use_L5_ADMIN_tool_for_changes"],
  "risk": {
    "level": "L0",
    "admin_write_tools_require_confirmation": true
  }
}
```

Admin write tools return, after confirmation:

```json
{
  "doctype": "User",
  "name": "alice@example.com",
  "docstatus": null,
  "status": "Admin Change Applied",
  "summary": "Updated roles for alice@example.com.",
  "next_actions": ["audit_change", "review_effective_access"],
  "risk": {
    "level": "L5_ADMIN",
    "confirmation_required": true,
    "confirmation_checked": true
  }
}
```

Raw ERPNext documents are kept in `debug.raw_document` for troubleshooting.

## Generic CRUD Boundary

Use generic tools only for safe reads of known records:

- `erpnext.get_document` for a specific `User`, `Role`, `Role Profile`, or `User Permission`
- `erpnext.get_doctype_schema` for schema inspection

Do not use generic `create_document`, `update_document`, or `delete_document` for Users & Permissions in agent-planned flows. Prefer the `erpnext.users.*` tools so `L5_ADMIN` risk and confirmation behavior remain visible.

## Not Implemented Yet

| Capability | Status |
| --- | --- |
| Previewing `DocPerm` / `Custom DocPerm` policy changes | Implemented as `erpnext.users.preview_permission_policy_change`. It is `L5_ADMIN` risk, preview-only, and does not write ERPNext. |
| Editing `DocPerm` / `Custom DocPerm` | Not implemented. Actual writes change system-wide permission policy and still require a dedicated confirmed `L5_ADMIN` write tool plus stronger local sandbox tests. |
| Password reset / API key reset | Not implemented. Requires dedicated bridge or Frappe method wrapper plus stronger confirmation. |
| Session revocation / logout all sessions | Not implemented. Needs Frappe method verification. |
| Role Profile role expansion preview | Implemented as `erpnext.users.preview_role_profile_roles`; a broader effective-access diff tool may still be needed. |
| Effective permission evaluation per user and DocType | Metadata-based preview implemented as `erpnext.users.preview_effective_permissions`; server-side check is wired through `erpnext.users.check_server_permission`, but broader differential testing against Frappe runtime policy is still needed. |

## Tests

Unit tests:

```powershell
pytest tests\test_users_permissions_tools.py -q
```

Current coverage:

- read result shape for `list_users`
- admin confirmation block with no ERPNext write call
- confirmed role assignment merge/update behavior
- access summary roles and user permissions shape
- metadata-based effective permission preview, including disabled-user handling
- server-side permission check dispatch, bridge result shape, and metadata/runtime difference reporting
- permission policy change preview/diff for add, update, and remove without ERPNext writes
- `ToolCall.infer_risk_level` for `L0` and `L5_ADMIN`

Safe local smoke tests can run read tools against the sandbox. Do not run `L5_ADMIN` write smoke tests against shared environments without explicit approval and disposable users/roles.
