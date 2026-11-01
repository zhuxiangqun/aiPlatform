#!/usr/bin/env bash
# Pi D2 admin/security pack check — shared baseline + edge boundary.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
BASE="${AIPLAT_SECURITY_BASELINE:-$ROOT/packages/aiplat-pi-runtime/security/baseline.yaml}"
[[ -f "$BASE" ]] || { echo "ERROR: missing $BASE" >&2; exit 2; }
export AIPLAT_SECURITY_BASELINE="$BASE"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
"$PY" "$ROOT/scripts/lib/aiplat_security_baseline.py" "$ROOT" "$BASE"

export AIPLAT_REPO_ROOT="$ROOT"
"$PY" - <<'PY'
from pathlib import Path
import os, re, sys
root = Path(os.environ["AIPLAT_REPO_ROOT"])
bin_http = root / "packages/aiplat-pi-runtime/bin/aiplat-http.mjs"
btext = bin_http.read_text(encoding="utf-8", errors="replace")
if re.search(r"aiPlat-platform|core\.harness|from core\.", btext):
    print("FAIL pi d2_admin_check:")
    print(" - aiplat-http.mjs imports platform/core")
    sys.exit(1)
print("OK pi d2 boundary (bin free of platform/core imports)")
print("OK pi d2_admin_check (enterprise remains opt-in; default off)")
PY
