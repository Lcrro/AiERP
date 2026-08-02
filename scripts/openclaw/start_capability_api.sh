#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$HOME/.config/nexterp/openclaw-nexterp.env"
VENV="$HOME/.local/share/nexterp-capability-api-v0.5/venv"
PIP_INDEX_URL="${NEXTERP_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE; run install_nexterp_runtime.sh first" >&2; exit 1; }
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c "import nexterp_agent, pydantic, psycopg" >/dev/null 2>&1; then
  PIP_DEFAULT_TIMEOUT=180 "$VENV/bin/pip" install --disable-pip-version-check --retries 5 \
    --index-url "$PIP_INDEX_URL" --upgrade "setuptools>=69" wheel
  PIP_DEFAULT_TIMEOUT=180 "$VENV/bin/pip" install --disable-pip-version-check --retries 5 \
    --index-url "$PIP_INDEX_URL" --no-build-isolation -e "$ROOT"
fi
set -a
source "$ENV_FILE"
set +a
cd "$ROOT"
exec "$VENV/bin/python" -m nexterp_agent.capability_service.server
