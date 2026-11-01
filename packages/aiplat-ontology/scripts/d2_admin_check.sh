#!/usr/bin/env bash
# Ontology D2 cohost admin/security pack check — shared baseline + hard gate.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
BASE="${AIPLAT_SECURITY_BASELINE:-$ROOT/packages/aiplat-ontology/security/baseline.yaml}"
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
man = (root / "capabilities.manifest.yaml").read_text(encoding="utf-8")
block = man.split("id: ontology", 1)[1].split("\n  - id:", 1)[0]
if "process_split_authorized: true" in block:
    print("FAIL ontology d2_admin_check:")
    print(" - manifest ontology process_split_authorized unexpectedly true")
    sys.exit(1)
print("OK ontology d2_admin_check (cohost; process_split stays unauthorized)")
PY
