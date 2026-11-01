#!/usr/bin/env bash
# Template D2 admin/security pack check — uses shared baseline checker.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
# REPLACE_ME: packages/<capability>/security/baseline.yaml
BASE="${AIPLAT_SECURITY_BASELINE:-$ROOT/packages/REPLACE_ME/security/baseline.yaml}"
[[ -f "$BASE" ]] || { echo "ERROR: missing $BASE" >&2; exit 2; }
export AIPLAT_SECURITY_BASELINE="$BASE"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
exec "$PY" "$ROOT/scripts/lib/aiplat_security_baseline.py" "$ROOT" "$BASE"
