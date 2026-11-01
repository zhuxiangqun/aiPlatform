#!/usr/bin/env bash
# FDE Field D2 admin/security pack check — shared baseline + signoff path.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
BASE="${AIPLAT_SECURITY_BASELINE:-$ROOT/packages/aiplat-fde/security/baseline.yaml}"
[[ -f "$BASE" ]] || { echo "ERROR: missing $BASE" >&2; exit 2; }
export AIPLAT_SECURITY_BASELINE="$BASE"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
"$PY" "$ROOT/scripts/lib/aiplat_security_baseline.py" "$ROOT" "$BASE"

export AIPLAT_REPO_ROOT="$ROOT"
"$PY" - <<'PY'
from pathlib import Path
import os, sys
root = Path(os.environ["AIPLAT_REPO_ROOT"])
errors = []
for rel in (
    "packages/aiplat-fde/docs/DATA_RESIDENCY.md",
    "packages/aiplat-fde/docs/D2_FIELD.md",
    "reports/five-products/ADR-FDE-FIELD-DEPLOY.md",
):
    p = root / rel
    if "acceptance/signoff" not in p.read_text(encoding="utf-8", errors="replace"):
        errors.append(f"signoff path missing in {rel}")
if errors:
    print("FAIL fde d2_admin_check:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK fde unique signoff path documented")
print("OK fde d2_admin_check (enterprise remains opt-in; default off)")
PY
