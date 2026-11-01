#!/usr/bin/env bash
# Evaluation D1/D2 upgrade — distinct version slot for runtime rollback.
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
echo "Evaluation upgrade → $VER_DIR (was: ${PREV:-none})"
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER_SLOT" "$PREFIX/current"
python3 - <<PY
import json, pathlib, datetime
p = pathlib.Path("$PREFIX") / "INSTALL_META.json"
meta = json.loads(p.read_text()) if p.exists() else {}
meta.update({
  "capability_id": "evaluation",
  "product_id": "evaluation",
  "deploy_unit": "central",
  "hosted_by": "aiplat",
  "version": "$VER",
  "version_slot": "$VER_SLOT",
  "upgraded_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
  "previous": "$PREV",
  "thin": True,
  "a3_split": False,
  "d2_cohost_pack": True,
})
p.write_text(json.dumps(meta, indent=2) + "\n")
PY
echo "PASS: Evaluation upgrade current=versions/$VER_SLOT"
