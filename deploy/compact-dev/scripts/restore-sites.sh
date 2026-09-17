#!/bin/bash
# Restore both Sites into the shared compact bench from verified backups.
# Never mounts old nexterp-material-* volumes for write.
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_common.sh"
load_backup_root

SITE_TEST="material-test.localhost"
SITE_V4="material-classification-v4.localhost"
DB_TEST="_2a2ea88640e22090"
DB_V4="_e0bea5d15b965dcc"

MYSQL_TEST="$BACKUP_ROOT/mysql/material-test-${DB_TEST}.sql.gz"
MYSQL_V4="$BACKUP_ROOT/mysql/classification-v4-${DB_V4}.sql.gz"
FILES_TEST="$BACKUP_ROOT/sites/material-test-site-files.tar.gz"
FILES_V4="$BACKUP_ROOT/sites/classification-v4-site-files.tar.gz"
CFG_TEST="$BACKUP_ROOT/sites/material-test-site_config.json"
CFG_V4="$BACKUP_ROOT/sites/classification-v4-site_config.json"

for f in "$MYSQL_TEST" "$MYSQL_V4" "$FILES_TEST" "$FILES_V4" "$CFG_TEST" "$CFG_V4"; do
  [[ -s "$f" ]] || { echo "error: missing/empty $f" >&2; exit 1; }
done

echo "[compact] Waiting for mariadb + app..."
for i in $(seq 1 60); do
  if compose exec -T mariadb healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1 \
     && compose exec -T nexterp-app true >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "error: stack not ready" >&2
    exit 1
  fi
done

echo "[compact] Writing common_site_config for compact network hosts..."
app_exec bash -lc "
set -e
mkdir -p sites
cat > sites/common_site_config.json <<'JSON'
{
  \"chromium_path\": \"/usr/bin/chromium-headless-shell\",
  \"db_host\": \"mariadb\",
  \"db_port\": 3306,
  \"redis_cache\": \"redis://redis-cache:6379\",
  \"redis_queue\": \"redis://redis-queue:6379\",
  \"redis_socketio\": \"redis://redis-queue:6379\",
  \"socketio_port\": 9000
}
JSON
printf '%s\n' erpnext frappe > sites/apps.txt
printf '%s\n%s\n' '${SITE_TEST}' '${SITE_V4}' > sites/sites.txt
printf '%s\n' '${SITE_TEST}' > sites/currentsite.txt
"

echo "[compact] Extracting site files into sites volume..."
TMP_HOST="$(mktemp -d /tmp/compact-restore.XXXXXX)"
cp "$FILES_TEST" "$TMP_HOST/material-test-site-files.tar.gz"
cp "$FILES_V4" "$TMP_HOST/classification-v4-site-files.tar.gz"
cp "$CFG_TEST" "$TMP_HOST/material-test-site_config.json"
cp "$CFG_V4" "$TMP_HOST/classification-v4-site_config.json"
cp "$MYSQL_TEST" "$TMP_HOST/material-test.sql.gz"
cp "$MYSQL_V4" "$TMP_HOST/classification-v4.sql.gz"

docker_cmd run --rm \
  -v nexterp-compact_sites:/sites \
  -v "$TMP_HOST":/backup:ro \
  --entrypoint bash \
  frappe/erpnext:v15.118.2 \
  -lc '
set -e
cd /sites
rm -rf material-test.localhost material-classification-v4.localhost
tar -xzf /backup/material-test-site-files.tar.gz
tar -xzf /backup/classification-v4-site-files.tar.gz
cp /backup/material-test-site_config.json material-test.localhost/site_config.json
cp /backup/classification-v4-site_config.json material-classification-v4.localhost/site_config.json
rm -f material-test.localhost/private/backups/*.sql.gz \
      material-classification-v4.localhost/private/backups/*.sql.gz 2>/dev/null || true
chown -R 1000:1000 material-test.localhost material-classification-v4.localhost || true
'

echo "[compact] Restoring MariaDB dumps into separate databases..."
SQL_OUT="$TMP_HOST/restore-all.sql"
python3 - "$TMP_HOST" "$SQL_OUT" <<'PY'
import json, gzip, sys
from pathlib import Path
tmp = Path(sys.argv[1])
out = Path(sys.argv[2])
chunks = []
for name in ("material-test.sql.gz", "classification-v4.sql.gz"):
    chunks.append(gzip.decompress((tmp / name).read_bytes()))
    chunks.append(b"\n")
for cfg_name, db in (
    ("material-test-site_config.json", "_2a2ea88640e22090"),
    ("classification-v4-site_config.json", "_e0bea5d15b965dcc"),
):
    cfg = json.loads((tmp / cfg_name).read_text())
    user = cfg["db_name"]
    pwd = cfg["db_password"].replace("\\", "\\\\").replace("'", "''")
    sql = f"""
CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{pwd}';
ALTER USER '{user}'@'%' IDENTIFIED BY '{pwd}';
GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'%';
FLUSH PRIVILEGES;
"""
    chunks.append(sql.encode())
out.write_bytes(b"".join(chunks))
PY
compose exec -T mariadb bash -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mariadb -uroot' < "$SQL_OUT"
rm -f "$SQL_OUT"

echo "[compact] Re-assert common_site_config + sites.txt after file restore..."
app_exec bash -lc "
set -e
cat > sites/common_site_config.json <<'JSON'
{
  \"chromium_path\": \"/usr/bin/chromium-headless-shell\",
  \"db_host\": \"mariadb\",
  \"db_port\": 3306,
  \"redis_cache\": \"redis://redis-cache:6379\",
  \"redis_queue\": \"redis://redis-queue:6379\",
  \"redis_socketio\": \"redis://redis-queue:6379\",
  \"socketio_port\": 9000
}
JSON
printf '%s\n' erpnext frappe > sites/apps.txt
printf '%s\n%s\n' '${SITE_TEST}' '${SITE_V4}' > sites/sites.txt
printf '%s\n' '${SITE_TEST}' > sites/currentsite.txt
rm -rf sites/assets
ln -s /home/frappe/frappe-bench/assets sites/assets
"

echo "[compact] Ensuring site logs directories..."
app_exec bash -lc "mkdir -p sites/material-test.localhost/logs sites/material-classification-v4.localhost/logs"

echo "[compact] Running bench migrate on both sites..."
app_exec bash -lc "bench --site $SITE_TEST migrate" || {
  echo "warn: migrate material-test returned non-zero; continuing to diagnose" >&2
}
app_exec bash -lc "bench --site $SITE_V4 migrate" || {
  echo "warn: migrate classification-v4 returned non-zero; continuing to diagnose" >&2
}

echo "[compact] Clearing cache..."
app_exec bash -lc "bench --site $SITE_TEST clear-cache" || true
app_exec bash -lc "bench --site $SITE_V4 clear-cache" || true

rm -rf "$TMP_HOST"
echo "[compact] Restore finished."
