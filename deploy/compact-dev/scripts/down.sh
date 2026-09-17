#!/bin/bash
# Stop compact stack WITHOUT removing volumes (-v forbidden).
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_common.sh"
echo "[compact] Stopping stack (volumes preserved)..."
compose down
echo "[compact] Done. Named volumes nexterp-compact_* left intact."
