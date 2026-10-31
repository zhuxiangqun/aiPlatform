#!/usr/bin/env bash
# Pi D2 admin/security pack check — file baseline only; does NOT enable enterprise.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASE="$ROOT/packages/aiplat-pi-runtime/security/baseline.yaml"
[[ -f "$BASE" ]] || { echo "ERROR: missing $BASE" >&2; exit 2; }

export AIPLAT_SECURITY_BASELINE="$BASE"
# Central checker uses d1_repo_root from central d1_lib — invoke via env + python inline instead
d1_require_python() {
  command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; return 2; }
}
d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_REPO_ROOT="$ROOT"
"$PY" - <<'PY'
from __future__ import annotations
import os, re, sys
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
text = Path(os.environ["AIPLAT_SECURITY_BASELINE"]).read_text(encoding="utf-8")
try:
    import yaml  # type: ignore
    data = yaml.safe_load(text)
except Exception:
    data = None

errors: list[str] = []
if data is None:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("path:"):
            rel = s.split(":", 1)[1].strip().strip('"').strip("'")
            if not (root / rel).exists():
                errors.append(f"missing {rel}")
else:
    for c in data.get("checks") or []:
        cid = c.get("id")
        rel = c.get("path")
        p = root / str(rel)
        if not p.is_file():
            errors.append(f"{cid}: missing {rel}")
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        for needle in c.get("must_contain") or []:
            if str(needle) not in body:
                errors.append(f"{cid}: missing snippet {needle!r} in {rel}")

bin_http = root / "packages/aiplat-pi-runtime/bin/aiplat-http.mjs"
btext = bin_http.read_text(encoding="utf-8", errors="replace")
if re.search(r"aiPlat-platform|core\.harness|from core\.", btext):
    errors.append("aiplat-http.mjs imports platform/core")

if errors:
    print("FAIL pi d2_admin_check:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

n = len((data or {}).get("checks") or [])
print(f"OK pi security baseline checks={n} file={os.environ['AIPLAT_SECURITY_BASELINE']}")
print("OK pi d2 boundary (bin free of platform/core imports)")
print("OK pi d2_admin_check (enterprise remains opt-in; default off)")
PY
