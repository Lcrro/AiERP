#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE="$HOME/.local/state/nexterp-openclaw-v0.5"
mkdir -p "$STATE"

stop_pid() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local pid
    pid="$(cat "$file")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      for _ in {1..30}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
      done
    fi
    rm -f "$file"
  fi
}

stop_pid "$STATE/capability-api.pid"
stop_pid "$STATE/gateway.pid"

nohup bash "$ROOT/scripts/openclaw/start_capability_api.sh" \
  >"$STATE/capability-api.log" 2>&1 </dev/null &
echo $! >"$STATE/capability-api.pid"

nohup bash "$ROOT/scripts/openclaw/start_nexterp_gateway.sh" \
  >"$STATE/gateway.log" 2>&1 </dev/null &
echo $! >"$STATE/gateway.pid"

sleep 5
for port in 8790 18829; do
  if ! grep -q ":$(printf '%04X' "$port")" /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
    echo "Port $port did not start" >&2
    tail -n 40 "$STATE/capability-api.log" "$STATE/gateway.log" >&2 || true
    exit 1
  fi
done

printf 'Capability API PID %s on 8790\n' "$(cat "$STATE/capability-api.pid")"
printf 'OpenClaw Gateway PID %s on 18829\n' "$(cat "$STATE/gateway.pid")"
