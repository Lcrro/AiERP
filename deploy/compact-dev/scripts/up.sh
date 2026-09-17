#!/bin/bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_common.sh"
cd "$COMPACT_ROOT"
echo "[compact] Building / starting 4-service stack..."
compose up -d --build "$@"
compose ps
