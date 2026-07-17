# Local Sandbox Operations

This document records how to run and verify the local WSL ERPNext/Nexterp sandbox.

## Current Environment

WSL bench path:

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

Site with ERPNext:

```text
localhost
```

Local URL:

```text
http://localhost:8001
```

Independent development site:

```text
http://localhost:8002
```

The `civil` profile points at this independent site. It contains the current UP
division master data used by the employee Agent workbench.

## Civil Golden Baseline

The `fac.localhost` test site can be restored to a clean, reproducible state
without deleting and rebuilding documents through the API one by one. The
baseline contains master data and test users, but no business transactions.

Create or replace the local golden baseline only after confirming that the site
has no business documents:

```powershell
.\scripts\test_env\create_civil_baseline.ps1
```

Restore the site and clear workbench conversations before a new test cycle:

```powershell
.\scripts\test_env\reset_civil_sandbox.ps1 -Confirm RESET-CIVIL-SANDBOX
```

Both scripts refuse to operate on any site other than `fac.localhost`. Backup
archives and their manifest are stored below `.secrets/civil-baselines/golden`
and are intentionally excluded from Git because the database snapshot contains
local test credentials. The reset script restores ERPNext through Bench, clears
the database using the site's own local credentials, clears ERPNext cache,
removes local workbench session files, and verifies that the business-document
inventory is zero. Database credentials are never printed or copied into the
repository.

Use this snapshot reset for sequential local acceptance tests. Parallel tests
should use separate ERPNext sites cloned from the same golden baseline so that
workers never share database state.

## Start Sandbox

From PowerShell:

```powershell
.\scripts\start_wsl_sandbox.ps1
```

Manual WSL equivalent:

```bash
cd ~/frappe-bench
redis-server config/redis_queue.conf --daemonize yes
redis-server config/redis_cache.conf --daemonize yes
bench start
```

This bench needs Redis queue/cache on ports:

```text
11000
13000
```

The web server runs on:

```text
8001
```

## Verify Sandbox

Ping Frappe:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8001/api/method/ping
```

Expected response:

```json
{"message":"pong"}
```

## Import v1 Master Data

The independent `civil` site can be initialized from the authoritative releases without direct database writes:

```powershell
python scripts\erpnext\import_master_data_release.py plan
python scripts\erpnext\import_master_data_release.py apply --profile civil
python scripts\erpnext\import_master_data_release.py verify --profile civil --workers 10
```

Large independent batches can be resumed safely:

```powershell
python scripts\erpnext\import_master_data_release.py apply --profile civil --doctype "Item Group" --workers 10
python scripts\erpnext\import_master_data_release.py apply --profile civil --doctype UOM --workers 10
python scripts\erpnext\import_master_data_release.py apply --profile civil --doctype Item --workers 15
python scripts\erpnext\import_master_data_release.py apply --profile civil --doctype "Item Price" --workers 20
```

The importer always uses ERPNext/Frappe APIs and supports `plan`, idempotent `apply`, and full `verify` modes.

Run adapter smoke checks after setting `NEXTERP_LOCAL_*` values:

```powershell
python scripts/smoke_erpnext.py --profile local --check auth
python scripts/smoke_erpnext.py --profile local --check customer
python scripts/smoke_erpnext.py --profile local --check bridge
python scripts/smoke_erpnext.py --profile local --check count
python scripts/smoke_erpnext.py --profile local --check todo-write
python scripts/smoke_erpnext.py --profile local --check attachment
python scripts/smoke_erpnext.py --profile local --check report
```

## Initialize Material Master Fields

Material master v0.1 adds custom fields to ERPNext `Item`.

After syncing `agent_bridge`, initialize or verify these fields:

```powershell
python scripts/setup_item_master.py --profile local
```

The command is repeatable. Existing fields are skipped.

## Clean Demo Data

Use the cleanup script to remove known ERPNext demo business records from the
local sandbox. The script uses the same ERPNext Adapter/API path as the agent
tool layer.

Preview what would be deleted:

```powershell
python scripts/clean_demo_data.py --profile local
```

Execute the cleanup:

```powershell
python scripts/clean_demo_data.py --profile local --execute
```

Also remove project-created smoke records:

```powershell
python scripts/clean_demo_data.py --profile local --execute --include-agent-tests
```

The script only targets known demo names such as `SKU001`-`SKU010`, `Demo Item
Group`, and the sample customers/suppliers created by the ERPNext demo setup.
Submitted documents are cancelled before deletion. Linked master records such as
Item, Customer, and Supplier are disabled when ERPNext refuses physical deletion.
Other records that are still linked are skipped and reported instead of being
force-deleted.

## agent_bridge

Local app path:

```text
/home/administrator/frappe-bench/apps/agent_bridge
```

Tracked mirror:

```text
frappe_apps/agent_bridge/
```

Sync tracked bridge API source to WSL:

```powershell
.\scripts\sync_agent_bridge.ps1
```

Current bridge methods:

```text
agent_bridge.api.ping
agent_bridge.api.submit_document
agent_bridge.api.cancel_document
agent_bridge.api.create_todo
agent_bridge.api.get_low_stock_items
agent_bridge.api.generate_purchase_suggestions
agent_bridge.api.create_material_request_draft
agent_bridge.api.create_sales_order_draft
agent_bridge.api.get_overdue_receivables_by_owner
agent_bridge.api.get_project_risks
agent_bridge.api.get_manager_exceptions
```

## Useful WSL Commands

List installed apps:

```bash
cd ~/frappe-bench
bench --site localhost list-apps
```

Inspect table fields:

```bash
bench --site localhost mariadb -e "desc tabBin;"
bench --site localhost mariadb -e "desc \`tabItem Reorder\`;"
```

Check listening ports:

```bash
ss -ltnp | grep -E ":(8001|11000|13000|9101)"
```
