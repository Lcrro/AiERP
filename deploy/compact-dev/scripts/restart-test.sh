#!/bin/bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_common.sh"

SITE_TEST="material-test.localhost"
SITE_V4="material-classification-v4.localhost"

echo "[restart] compose stop..."
compose stop
echo "[restart] compose start..."
compose start

echo "[restart] waiting for healthy app..."
for i in $(seq 1 60); do
  if compose exec -T nexterp-app /usr/local/bin/compact-healthcheck.sh >/dev/null 2>&1; then
    break
  fi
  sleep 3
  if [[ $i -eq 60 ]]; then
    echo "error: app not healthy after restart" >&2
    compose exec -T nexterp-app supervisorctl -c /home/frappe/supervisord-compact.conf status || true
    exit 1
  fi
done

count_items() {
  local site="$1"
  app_exec bash -lc "bench --site $site mariadb -N -e 'SELECT COUNT(*) FROM tabItem;'" | tr -d '[:space:]'
}

c1="$(count_items "$SITE_TEST")"
c2="$(count_items "$SITE_V4")"
echo "[restart] Items material-test=$c1 classification-v4=$c2"
if [[ "$c1" == "259" && "$c2" == "917" ]]; then
  echo "restart_ok YES"
  exit 0
fi
echo "restart_ok NO"
exit 1
