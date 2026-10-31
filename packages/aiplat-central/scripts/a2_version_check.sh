#!/usr/bin/env bash
# A2 versioning gate — versions.yaml ↔ package.json ↔ module.yaml.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
SSOT="${AIPLAT_VERSIONS_YAML:-$ROOT/reports/five-products/versions.yaml}"
[[ -f "$SSOT" ]] || { echo "ERROR: missing $SSOT" >&2; exit 2; }

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_REPO_ROOT="$ROOT"
export AIPLAT_VERSIONS_YAML="$SSOT"

"$PY" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
ssot_path = Path(os.environ["AIPLAT_VERSIONS_YAML"])
text = ssot_path.read_text(encoding="utf-8")

try:
    import yaml  # type: ignore
    data = yaml.safe_load(text)
except Exception as e:
    print(f"ERROR: need PyYAML to parse versions.yaml: {e}", file=sys.stderr)
    sys.exit(2)

errors: list[str] = []
caps = data.get("capabilities") or []
if not caps:
    errors.append("capabilities empty")

def parts(s: str):
    out = []
    for x in str(s).split("."):
        try:
            out.append(int("".join(ch for ch in x if ch.isdigit()) or "0"))
        except ValueError:
            out.append(0)
    return out

for c in caps:
    cid = c.get("id")
    want = str(c.get("version") or "")
    pj = root / str(c.get("package_json") or "")
    my = root / str(c.get("module_yaml") or "")
    if not pj.is_file():
        errors.append(f"{cid}: missing package.json {pj}")
        continue
    if not my.is_file():
        errors.append(f"{cid}: missing module.yaml {my}")
        continue
    pkg_ver = str(json.loads(pj.read_text(encoding="utf-8")).get("version") or "")
    # module.yaml: prefer PyYAML; fallback line scan
    mod = None
    try:
        import yaml as _y
        mod = _y.safe_load(my.read_text(encoding="utf-8"))
    except Exception:
        mod = None
    if isinstance(mod, dict):
        mod_ver = str(mod.get("version") or "")
    else:
        mod_ver = ""
        for line in my.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version:"):
                mod_ver = line.split(":", 1)[1].strip().strip('"').strip("'")
                break
    if pkg_ver != want:
        errors.append(f"{cid}: package.json={pkg_ver!r} != ssot={want!r}")
    if mod_ver != want:
        errors.append(f"{cid}: module.yaml={mod_ver!r} != ssot={want!r}")

# Compat matrix min_version ≤ package version
matrix = root / "packages/aiplat-central/compat/matrix.yaml"
if matrix.is_file():
    try:
        import yaml as _y
        mx = _y.safe_load(matrix.read_text(encoding="utf-8"))
    except Exception:
        mx = None
    if isinstance(mx, dict):
        by_id = {c.get("id"): c for c in caps}
        for u in mx.get("units") or []:
            uid = u.get("id")
            # matrix uses aiplat-central / pi-runtime ids — map loosely
            key = uid
            if uid == "aiplat-central":
                key = "aiplat"
            if uid == "pi-runtime":
                key = "pi"
            cap = by_id.get(key)
            if not cap:
                continue
            min_v = str(u.get("min_version") or "0.0.0")
            ver = str(cap.get("version") or "0.0.0")
            if parts(ver) < parts(min_v):
                errors.append(f"compat {uid}: version {ver} < min_version {min_v}")

if errors:
    print("FAIL a2 version check:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print(f"OK a2 version check capabilities={len(caps)} ssot={ssot_path}")
PY
