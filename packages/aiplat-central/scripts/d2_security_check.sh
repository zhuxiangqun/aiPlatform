#!/usr/bin/env bash
# D2+ Thin — admin/security baseline file checks (no live MFA enrollment).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
BASE="${AIPLAT_SECURITY_BASELINE:-$ROOT/packages/aiplat-central/security/baseline.yaml}"
[[ -f "$BASE" ]] || { echo "ERROR: missing $BASE" >&2; exit 2; }

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
exec "$PY" "$ROOT/scripts/lib/aiplat_security_baseline.py" "$ROOT" "$BASE"
