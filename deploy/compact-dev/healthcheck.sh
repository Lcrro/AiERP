#!/bin/bash
set -euo pipefail
SUPERVISOR_CONF="${SUPERVISOR_CONF:-/home/frappe/supervisord-compact.conf}"
REQUIRED=(nginx backend websocket scheduler queue-short queue-long)
STATUS="$(/usr/bin/supervisorctl -c "$SUPERVISOR_CONF" status 2>/dev/null || true)"
if [[ -z "$STATUS" ]]; then
  echo "supervisor unavailable"
  exit 1
fi
for prog in "${REQUIRED[@]}"; do
  line="$(printf '%s\n' "$STATUS" | awk -v p="$prog" '$1==p {print; exit}')"
  if [[ -z "$line" ]] || ! printf '%s' "$line" | grep -q RUNNING; then
    echo "unhealthy: $prog -> ${line:-missing}"
    exit 1
  fi
done
if ! bash -c 'echo > /dev/tcp/127.0.0.1/8080' 2>/dev/null; then
  echo "unhealthy: port 8080 closed"
  exit 1
fi
exit 0
