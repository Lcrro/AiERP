# AiERP Compact Dev Stack (Plan A)

Reduce two 9-container DinD stacks (18 containers) to **4 containers** while keeping
two isolated Sites on one Frappe bench:

| Site | Host port | Host header |
|------|-----------|-------------|
| `material-test.localhost` | 8003 | `material-test.localhost` |
| `material-classification-v4.localhost` | 8004 | `material-classification-v4.localhost` |

## Services

1. `nexterp-app` — nginx + gunicorn + socketio + scheduler + queue-short + queue-long (supervisord)
2. `mariadb` — shared server, **separate DB per Site**
3. `redis-cache`
4. `redis-queue`

Image pin: **`frappe/erpnext:v15.118.2`** (no upgrade). MariaDB 11.8 / Redis 8.6-alpine
match the prior material stacks.

## Named volumes (NEW — never reuse old volumes for write)

- `nexterp-compact_db-data`
- `nexterp-compact_sites`
- `nexterp-compact_redis-queue-data`

Old volumes `nexterp-material-test_*` and `nexterp-material-classification-v4_*` must
remain listed and untouched.

## Secrets

Put real values in `.secrets/erpnext-compact/stack.env` (gitignored). See `.env.example`.
Never commit DB passwords, site encryption keys, or API credentials.

## Ops

```bash
# 1) Verify backups
./scripts/backup-verify.sh

# 2) Stop old dual stacks WITHOUT -v (frees vfs layers; keeps old volumes)
python scripts/test_env/material_sites.py --site material-test --action stop
python scripts/test_env/material_sites.py --site classification-v4 --action stop

# 3) Build & start compact stack (empty NEW volumes)
./scripts/up.sh

# 4) Restore Sites from backup root into NEW volumes
./scripts/restore-sites.sh

# 5) Smoke: Host routing, 259/917 counts, isolation
./scripts/smoke.sh

# 6) Restart persistence
./scripts/restart-test.sh

# Stop compact (volumes kept)
./scripts/down.sh
```

Workbench stays host-side on `:8788`. Existing env Host headers (`NEXTERP_*_HOST_HEADER`)
continue to work against 8003/8004.

Thin lifecycle wrapper (does not replace dual-stack `material_sites.py`):

```bash
python scripts/test_env/compact_stack.py --action status|up|down|restore|smoke|restart-test
```

## Rollback

1. `./scripts/down.sh` (no `-v`)
2. Start old stacks: `material_sites.py --site … --action start` (reattaches **old** volumes)
3. Confirm Item counts 259 / 917 on old ports

If restore fails, leave old volumes intact and document `COMPACT_STACK_BLOCKED`.

## Hard constraints

- Do not `docker compose down -v`, prune volumes, or delete `nexterp-material-*` volumes
- Do not modify `main`; stay on feature branch
- Do not change AiERP business / classification rules
- Do not put secrets in git, reports, or ordinary logs
