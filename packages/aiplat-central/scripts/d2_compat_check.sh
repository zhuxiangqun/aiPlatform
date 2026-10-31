#!/usr/bin/env bash
# D2 Thin — validate compat matrix paths, package versions, healthz product_id consts.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
MATRIX="${AIPLAT_COMPAT_MATRIX:-$ROOT/packages/aiplat-central/compat/matrix.yaml}"
[[ -f "$MATRIX" ]] || { echo "ERROR: missing matrix $MATRIX" >&2; exit 2; }

d1_require_python
PY=python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
fi

export AIPLAT_COMPAT_MATRIX="$MATRIX"
export AIPLAT_REPO_ROOT="$ROOT"

"$PY" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
matrix_path = Path(os.environ["AIPLAT_COMPAT_MATRIX"])
text = matrix_path.read_text(encoding="utf-8")

try:
    import yaml  # type: ignore
    data = yaml.safe_load(text)
except Exception:
    # Minimal YAML subset: only need units/contracts lists with scalar fields.
    # Prefer PyYAML; fallback parses via json after a tiny converter is not worth it —
    # require paths exist via line scan if yaml missing.
    data = None

errors: list[str] = []

def fail(msg: str) -> None:
    errors.append(msg)

if data is None:
    # Fallback: ensure referenced paths from matrix file exist (grep-style)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for key in ("package:", "version_file:", "healthz_schema:", "smoke:", "path:"):
            if line.startswith(key):
                rel = line.split(":", 1)[1].strip().strip('"').strip("'")
                p = root / rel
                if not p.exists():
                    fail(f"missing path {rel}")
    if errors:
        print("FAIL compat (no PyYAML, path scan):")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("OK compat path-scan (PyYAML unavailable)")
    sys.exit(0)

units = data.get("units") or []
contracts = data.get("contracts") or []
if not units:
    fail("units empty")

for u in units:
    uid = u.get("id")
    for key in ("package", "version_file", "healthz_schema", "smoke"):
        rel = u.get(key)
        if not rel:
            fail(f"{uid}: missing {key}")
            continue
        if not (root / rel).exists():
            fail(f"{uid}: missing {rel}")
    vf = root / str(u.get("version_file") or "")
    if vf.is_file():
        ver = json.loads(vf.read_text(encoding="utf-8")).get("version", "0.0.0")
        min_v = str(u.get("min_version") or "0.0.0")
        # semver-ish: compare dotted ints left-to-right
        def parts(s: str):
            out = []
            for x in s.split("."):
                try:
                    out.append(int(x))
                except ValueError:
                    out.append(0)
            return out
        if parts(ver) < parts(min_v):
            fail(f"{uid}: version {ver} < min_version {min_v}")
    hs = root / str(u.get("healthz_schema") or "")
    if hs.is_file():
        schema = json.loads(hs.read_text(encoding="utf-8"))
        const = ((schema.get("properties") or {}).get("product_id") or {}).get("const")
        want = u.get("product_id")
        if want and const != want:
            fail(f"{uid}: healthz product_id const={const!r} want={want!r}")

for c in contracts:
    cid = c.get("id")
    rel = c.get("path")
    if not rel or not (root / rel).exists():
        fail(f"contract {cid}: missing {rel}")

if errors:
    print("FAIL compat matrix:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print(f"OK compat matrix units={len(units)} contracts={len(contracts)} file={matrix_path}")
PY
