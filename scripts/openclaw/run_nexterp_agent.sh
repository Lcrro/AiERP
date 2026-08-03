#!/usr/bin/env bash
set -euo pipefail

RUNTIME="$HOME/.local/share/nexterp-openclaw-v0.5"
NODE_HOME="$RUNTIME/node-v22.22.3-linux-x64"
OPENCLAW="$RUNTIME/cli/node_modules/.bin/openclaw"
ENV_FILE="$HOME/.config/nexterp/openclaw-nexterp.env"
EXTERNAL_SUBJECT=""

if [[ "${1:-}" == "--external-subject" ]]; then
  EXTERNAL_SUBJECT="${2:-}"
  if [[ -z "$EXTERNAL_SUBJECT" ]]; then
    echo "--external-subject requires a value" >&2
    exit 2
  fi
  shift 2
fi

if [[ ! -x "$OPENCLAW" ]]; then
  echo "OpenClaw v0.5 runtime is not installed" >&2
  exit 2
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "OpenClaw v0.5 environment file is missing" >&2
  exit 2
fi

export PATH="$NODE_HOME/bin:$PATH"
set -a
source "$ENV_FILE"
set +a

if [[ -n "$EXTERNAL_SUBJECT" ]]; then
  export NEXTERP_OPENCLAW_DEV_SUBJECT="$EXTERNAL_SUBJECT"
fi

exec "$OPENCLAW" --profile nexterp agent "$@"
