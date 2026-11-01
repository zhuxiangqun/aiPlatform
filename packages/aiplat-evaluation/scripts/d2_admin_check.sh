#!/usr/bin/env bash
# Evaluation D2 cohost admin/security pack check — file baseline only.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
BASE="$ROOT/packages/aiplat-evaluation/security/baseline.yaml"
[[ -f "$BASE" ]] || { echo "ERROR: missing $BASE" >&2; exit 2; }

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_REPO_ROOT="$ROOT"
export AIPLAT_SECURITY_BASELINE="$BASE"

"$PY" - <<'PY'
from __future__ import annotations
import os, sys
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

man = (root / "capabilities.manifest.yaml").read_text(encoding="utf-8")
if "id: evaluation" in man and "process_split_authorized: true" in man.split("id: evaluation", 1)[1].split("\n  - id:", 1)[0]:
    errors.append("manifest evaluation process_split_authorized unexpectedly true")

if errors:
    print("FAIL evaluation d2_admin_check:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

n = len((data or {}).get("checks") or [])
print(f"OK evaluation security baseline checks={n}")
print("OK evaluation d2_admin_check (cohost; process_split stays unauthorized)")
PY
