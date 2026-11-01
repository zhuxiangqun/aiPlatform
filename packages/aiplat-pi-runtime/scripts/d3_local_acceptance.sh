#!/usr/bin/env bash
# Pi D3 local acceptance — delegates to d3_local_closeout (already UAT-grade local).
# Never d3_production authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/d3_local_closeout.sh"
