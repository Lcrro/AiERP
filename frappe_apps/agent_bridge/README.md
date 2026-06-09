# agent_bridge

`agent_bridge` is a small Frappe app that exposes stable whitelisted methods for employee agents.

It is for operations that are awkward or fragile through generic DocType REST calls, such as:

- submit/cancel a document through normal Frappe rules
- create agent-generated ToDo records
- query business-specific exceptions
- later: generate purchase suggestions, follow-up lists, and management summaries

## Current WSL Install

The local sandbox app was created at:

```text
/home/administrator/frappe-bench/apps/agent_bridge
```

And installed on:

```text
localhost
```

Check it from the adapter:

```powershell
$env:NEXTERP_LOCAL_BASE_URL='http://localhost:8001'
$env:NEXTERP_LOCAL_API_KEY='...'
$env:NEXTERP_LOCAL_API_SECRET='...'
python scripts/smoke_erpnext.py --profile local --check bridge
```

## Sync Note

The tracked API source here mirrors:

```text
/home/administrator/frappe-bench/apps/agent_bridge/agent_bridge/api.py
```

