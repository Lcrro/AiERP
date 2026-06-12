# Nexterp Agent

Nexterp Agent is an ERPNext/Nexterp assistant layer. The long-term goal is for employees to work through role-aware agents instead of manually navigating ERP menus and forms.

Current engineering focus:

```text
User speaks naturally
  -> Agent translates intent into ToolCall
  -> ERPNext Adapter executes ToolCall
  -> ERPNext returns ToolResult
  -> Agent explains result in natural language
```

The implemented foundation currently covers the backend tool channel:

```text
ToolCall
  -> ERPNext Adapter
  -> ERPNext / Frappe API
  -> ToolResult
```

## Quick Start

Install the Python package:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

Run tests:

```powershell
python -m pytest -q
```

Start the local WSL ERPNext sandbox:

```powershell
.\scripts\start_wsl_sandbox.ps1
```

Run local smoke checks after filling `NEXTERP_LOCAL_*` values:

```powershell
python scripts/smoke_erpnext.py --profile local --check auth
python scripts/smoke_erpnext.py --profile local --check customer
python scripts/smoke_erpnext.py --profile local --check bridge
python scripts/smoke_erpnext.py --profile local --check todo-write
python scripts/smoke_erpnext.py --profile local --check attachment
python scripts/smoke_erpnext.py --profile local --check report
```

## Documentation

Start here:

- [Documentation Index](docs/README.md)
- [Architecture Roadmap](docs/architecture/roadmap.md)
- [Project Structure And Boundaries](docs/architecture/project-structure.md)
- [DocType Index Design](docs/architecture/doctype-index.md)
- [ERPNext Capability Map](docs/reference/erpnext-capability-map.md)
- [Material Master Standard](docs/reference/material-master-standard.md)
- [Tool Layer v0.1 Checklist](docs/planning/tool-layer-v0.1.md)
- [Item Master Search v0.1 Plan](docs/planning/item-master-search-v0.1.md)
- [Local Sandbox Operations](docs/operations/local-sandbox.md)

## Repository Layout

```text
src/nexterp_agent/             Python package
  agent_runtime/               Future natural-language brain: routing, state, planning
  erpnext/                     ERPNext ToolCall schemas, adapter, client, risk policy
  item_master/                 Material master rules, coding, search, PostgreSQL catalog
  scenarios/                   Future reusable business scenario runners
frappe_apps/agent_bridge/      Tracked mirror of the local Frappe bridge app
scripts/                       Compatibility wrappers plus categorized script folders
  dev/                         Local sandbox, sync, smoke checks
  erpnext/                     ERPNext setup, cleanup, import, verification
  material_master/             Material data processing, governance, search evaluation
  scenarios/                   Business sandbox seed, runner, coverage checks
data/                          Local data assets and generated reports
docs/                          Project documentation
tools/                         Local viewer/debug pages
tests/                         Unit, integration, and future scenario tests
```

## Current Local Sandbox

The current machine has a WSL ERPNext bench at:

```text
/home/administrator/frappe-bench
```

The discovered local ERPNext URL is:

```text
http://localhost:8001
```

See [Local Sandbox Operations](docs/operations/local-sandbox.md) for details.
