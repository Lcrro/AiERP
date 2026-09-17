#!/bin/bash
# Shared helpers for compact-dev scripts. Secrets stay out of stdout.
set -euo pipefail
export PATH="/home/box/bin:${PATH:-}"

COMPACT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$COMPACT_ROOT/../.." && pwd)"
SECRET_ENV="${COMPACT_SECRET_ENV:-$REPO_ROOT/.secrets/erpnext-compact/stack.env}"
DEFAULT_BACKUP_ROOT="/home/box/secure-transfer/aierp-compact-backups/20260917-101121"

docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
    return
  fi
  local q=""
  local a
  for a in "$@"; do
    q+=" $(printf '%q' "$a")"
  done
  sg docker -c "docker${q}"
}

compose() {
  local args=(compose --project-directory "$COMPACT_ROOT" -f "$COMPACT_ROOT/docker-compose.yml")
  if [[ -f "$SECRET_ENV" ]]; then
    args+=(--env-file "$SECRET_ENV")
  elif [[ -f "$COMPACT_ROOT/.env" ]]; then
    args+=(--env-file "$COMPACT_ROOT/.env")
  else
    echo "error: missing env file at $SECRET_ENV (or $COMPACT_ROOT/.env)" >&2
    exit 1
  fi
  docker_cmd "${args[@]}" "$@"
}

load_backup_root() {
  BACKUP_ROOT="${BACKUP_ROOT:-}"
  if [[ -z "$BACKUP_ROOT" && -f "$SECRET_ENV" ]]; then
    BACKUP_ROOT="$(grep -E '^BACKUP_ROOT=' "$SECRET_ENV" | head -1 | cut -d= -f2- || true)"
  fi
  BACKUP_ROOT="${BACKUP_ROOT:-$DEFAULT_BACKUP_ROOT}"
}

app_exec() {
  compose exec -T nexterp-app "$@"
}
