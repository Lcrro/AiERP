#!/bin/bash
set -euo pipefail

ASSETS_PATH="/home/frappe/frappe-bench/sites/assets"
BAKED_PATH="/home/frappe/frappe-bench/assets"
SUPERVISOR_CONF="${SUPERVISOR_CONF:-/home/frappe/supervisord-compact.conf}"

echo "[compact] Linking fresh assets to volume..."
rm -rf "$ASSETS_PATH"
mkdir -p "$(dirname "$ASSETS_PATH")"
ln -s "$BAKED_PATH" "$ASSETS_PATH"

export BACKEND="${BACKEND:-127.0.0.1:8000}"
export SOCKETIO="${SOCKETIO:-127.0.0.1:9000}"
export UPSTREAM_REAL_IP_ADDRESS="${UPSTREAM_REAL_IP_ADDRESS:-127.0.0.1}"
export UPSTREAM_REAL_IP_HEADER="${UPSTREAM_REAL_IP_HEADER:-X-Forwarded-For}"
export UPSTREAM_REAL_IP_RECURSIVE="${UPSTREAM_REAL_IP_RECURSIVE:-off}"
# shellcheck disable=SC2016
export FRAPPE_SITE_NAME_HEADER="${FRAPPE_SITE_NAME_HEADER:-\$host}"
export PROXY_READ_TIMEOUT="${PROXY_READ_TIMEOUT:-120}"
export CLIENT_MAX_BODY_SIZE="${CLIENT_MAX_BODY_SIZE:-50m}"

echo "[compact] Rendering nginx config (site header=${FRAPPE_SITE_NAME_HEADER})..."
# shellcheck disable=SC2016
envsubst '${BACKEND}
  ${SOCKETIO}
  ${UPSTREAM_REAL_IP_ADDRESS}
  ${UPSTREAM_REAL_IP_HEADER}
  ${UPSTREAM_REAL_IP_RECURSIVE}
  ${FRAPPE_SITE_NAME_HEADER}
  ${PROXY_READ_TIMEOUT}
  ${CLIENT_MAX_BODY_SIZE}' \
  </templates/nginx/frappe.conf.template >/etc/nginx/conf.d/frappe.conf

term_handler() {
  echo "[compact] Caught signal — shutting down supervised children..."
  /usr/bin/supervisorctl -c "$SUPERVISOR_CONF" shutdown || true
  # Give children a moment; supervisord will exit
  sleep 2
  exit 0
}
trap term_handler SIGTERM SIGINT

echo "[compact] Starting process supervisor..."
exec "$@"
