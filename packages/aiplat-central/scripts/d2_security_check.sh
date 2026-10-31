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

export AIPLAT_REPO_ROOT="$ROOT"
export AIPLAT_SECURITY_BASELINE="$BASE"

"$PY" - <<'PY'
from __future__ import annotations

import os
import sys
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
    # Fallback: ensure referenced paths exist
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("path:"):
            rel = s.split(":", 1)[1].strip().strip('"').strip("'")
            if not (root / rel).exists():
                errors.append(f"missing {rel}")
    if errors:
        print("FAIL security baseline (path scan):")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("OK security baseline path-scan (PyYAML unavailable)")
    sys.exit(0)

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

if errors:
    print("FAIL security baseline:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

n = len(data.get("checks") or [])
print(f"OK security baseline checks={n} file={os.environ['AIPLAT_SECURITY_BASELINE']}")
PY
