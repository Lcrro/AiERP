#!/bin/bash
# Host-header routing + Item count smoke checks (GPC 259 / V4 917).
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_common.sh"

SITE_TEST="material-test.localhost"
SITE_V4="material-classification-v4.localhost"
PORT_TEST="${HTTP_PORT_TEST:-8003}"
PORT_V4="${HTTP_PORT_V4:-8004}"
EXPECT_TEST=259
EXPECT_V4=917

http_code() {
  local port="$1" host="$2"
  curl -s -o /dev/null -w '%{http_code}' -H "Host: $host" "http://127.0.0.1:${port}/" || echo "000"
}

count_items() {
  local site="$1"
  app_exec bash -lc "bench --site $site mariadb -N -e 'SELECT COUNT(*) FROM tabItem;'" | tr -d '[:space:]'
}

echo "[smoke] HTTP Host-header checks..."
code_test="$(http_code "$PORT_TEST" "$SITE_TEST")"
code_v4="$(http_code "$PORT_V4" "$SITE_V4")"
code_test_on_v4port="$(http_code "$PORT_V4" "$SITE_TEST")"
code_v4_on_testport="$(http_code "$PORT_TEST" "$SITE_V4")"

echo "  $SITE_TEST via :$PORT_TEST -> HTTP $code_test"
echo "  $SITE_V4 via :$PORT_V4 -> HTTP $code_v4"
echo "  $SITE_TEST via :$PORT_V4 -> HTTP $code_test_on_v4port"
echo "  $SITE_V4 via :$PORT_TEST -> HTTP $code_v4_on_testport"

echo "[smoke] Item counts..."
count_test="$(count_items "$SITE_TEST")"
count_v4="$(count_items "$SITE_V4")"
echo "  $SITE_TEST Items=$count_test (expect $EXPECT_TEST)"
echo "  $SITE_V4 Items=$count_v4 (expect $EXPECT_V4)"

echo "[smoke] Isolation probe (write on test must not appear on v4)..."
NOTE_TITLE="compact-isolation-$(date +%s)"
NOTE_NAME="COMPACT-ISO-$(date +%s)"
app_exec bash -lc "bench --site $SITE_TEST mariadb -e \"
INSERT INTO tabNote (name, creation, modified, modified_by, owner, docstatus, idx, title, public, notify_on_login, notify_on_every_login)
VALUES ('${NOTE_NAME}', NOW(), NOW(), 'Administrator', 'Administrator', 0, 0, '${NOTE_TITLE}', 0, 0, 0);
\""
on_test="$(app_exec bash -lc "bench --site $SITE_TEST mariadb -N -e \"SELECT COUNT(*) FROM tabNote WHERE name='${NOTE_NAME}';\"" | tr -d '[:space:]')"
on_v4="$(app_exec bash -lc "bench --site $SITE_V4 mariadb -N -e \"SELECT COUNT(*) FROM tabNote WHERE name='${NOTE_NAME}';\"" | tr -d '[:space:]')"
app_exec bash -lc "bench --site $SITE_TEST mariadb -e \"DELETE FROM tabNote WHERE name='${NOTE_NAME}';\"" >/dev/null 2>&1 || true

echo "  note_count_test=${on_test} note_count_v4=${on_v4} (expect test=1 v4=0)"

ok=1
[[ "$code_test" =~ ^(200|301|302)$ ]] || { echo "fail http test"; ok=0; }
[[ "$code_v4" =~ ^(200|301|302)$ ]] || { echo "fail http v4"; ok=0; }
[[ "$count_test" == "$EXPECT_TEST" ]] || { echo "fail count test"; ok=0; }
[[ "$count_v4" == "$EXPECT_V4" ]] || { echo "fail count v4"; ok=0; }
[[ "${on_test}" == "1" && "${on_v4}" == "0" ]] || { echo "fail isolation"; ok=0; }

if [[ $ok -eq 1 ]]; then
  echo "smoke_ok YES"
  exit 0
fi
echo "smoke_ok NO"
exit 1
