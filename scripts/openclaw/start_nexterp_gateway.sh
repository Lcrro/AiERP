#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$HOME/.config/nexterp/openclaw-nexterp.env"
RUNTIME="$HOME/.local/share/nexterp-openclaw-v0.5"
NODE_HOME="$RUNTIME/node-v22.22.3-linux-x64"
OPENCLAW="$RUNTIME/cli/node_modules/.bin/openclaw"

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE; run install_nexterp_runtime.sh first" >&2; exit 1; }
set -a
source "$ENV_FILE"
set +a
export PATH="$NODE_HOME/bin:$PATH"

exec "$OPENCLAW" --profile nexterp gateway run \
  --port 18829 --bind loopback --auth token --token "$OPENCLAW_GATEWAY_TOKEN"
