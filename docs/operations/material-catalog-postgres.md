# Material Catalog PostgreSQL Operations

This runbook starts the local PostgreSQL database used by the Agent material search catalog.

## Local Connection

The local development DSN is:

```text
postgresql://nexterp_agent:nexterp_agent_dev@localhost:55433/nexterp_agent
```

It is intentionally on host port `55433` to avoid conflicting with any existing PostgreSQL on `5432`.

## Start

```powershell
docker compose up -d material-catalog-postgres
```

## Import Reviewed Catalog

```powershell
$env:MATERIAL_CATALOG_DATABASE_URL="postgresql://nexterp_agent:nexterp_agent_dev@localhost:55433/nexterp_agent"
python scripts/import_review_catalog_to_postgres.py
```

Expected current import counts:

```json
{
  "groups": 641,
  "group_mappings": 641,
  "items": 2355,
  "aliases": 2400,
  "manual_review": 803,
  "services": 118
}
```

## Stop

```powershell
docker compose stop material-catalog-postgres
```

## Reset Data

This removes the local PostgreSQL volume and all imported catalog data:

```powershell
docker compose down -v
```
