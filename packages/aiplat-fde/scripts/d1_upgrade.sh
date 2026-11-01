#!/usr/bin/env bash
# FDE Field D1/D2 upgrade — new version slot; keep previous for --runtime rollback.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_python
PREFIX="$(d1_prefix)"
VER="$(d1_pkg_version)"
PREV=""
if [[ -L "$PREFIX/current" || -d "$PREFIX/current" ]]; then
  PREV="$(readlink "$PREFIX/current" 2>/dev/null || true)"
fi

mkdir -p "$PREFIX"
echo "${PREV:-}" >"$PREFIX/.previous_current"

VER_SLOT="$VER"
VER_DIR="$PREFIX/versions/$VER_SLOT"
if [[ -d "$VER_DIR" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  VER_SLOT="${VER}+${STAMP}"
  VER_DIR="$PREFIX/versions/$VER_SLOT"
fi
echo "FDE Field upgrade → $VER_DIR (was: ${PREV:-none})"
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER_SLOT" "$PREFIX/current"

python3 - <<PY
import json, pathlib, datetime
p = pathlib.Path("$PREFIX") / "INSTALL_META.json"
meta = {}
if p.exists():
    meta = json.loads(p.read_text())
meta.update({
  "capability_id": "fde",
  "product_id": "fde",
  "deploy_unit": "field",
  "version": "$VER",
  "version_slot": "$VER_SLOT",
  "prefix": "$PREFIX",
  "upgraded_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
  "previous": "$PREV",
  "production_field": True,
  "field_d1_adr": "accepted",
  "field_d2_pack": True,
})
p.write_text(json.dumps(meta, indent=2) + "\n")
PY

echo "PASS: FDE Field upgrade current=versions/$VER_SLOT previous=${PREV:-none}"
