#!/usr/bin/env bash
# Package release readiness (ARCH v1.3) — version + contracts SSOT + unit slice.
# NEVER sets process_split_authorized=true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

PKG_JSON="$ROOT/package.json"
[[ -f "$PKG_JSON" ]] || { echo "REFUSE: missing package.json" >&2; exit 2; }

VER="$(python3 -c "import json; print(json.load(open('$PKG_JSON'))['version'])")"
[[ -n "$VER" ]] || { echo "REFUSE: empty version" >&2; exit 2; }
echo "== version $VER =="

python3 "$ROOT/contracts/validate_sample.py"

PYTHONPATH=. python3 -m pytest \
  tests/test_arch_consolidation_v1.py \
  tests/test_scorecard_v1.py \
  -q --tb=line

# Contracts SSOT: reports must not carry divergent schema copies.
python3 - <<PY
from pathlib import Path
repo = Path("$REPO")
pkg = repo / "packages/aiplat-evaluation/contracts/schemas"
reports = repo / "docs/products/five-products/modules/evaluation/contracts/schemas"
assert pkg.is_dir()
# JSON files under reports/schemas are forbidden (README-only shim).
json_files = sorted(p.name for p in reports.glob("*.json"))
assert json_files == [], f"reports schemas drift (must be empty): {json_files}"
print("contracts SSOT ok", {"package_schemas": len(list(pkg.glob('*.json'))), "version": "$VER"})
PY

echo "package_release_check PASS version=$VER authorize=false"
