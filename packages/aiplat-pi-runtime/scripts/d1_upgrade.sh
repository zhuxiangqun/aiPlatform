#!/usr/bin/env bash
# Pi D1 upgrade — install new package version; keep previous under versions/ for rollback.
# Bundle-first preferred (point AIPLAT_APP_HOME / bundles/current); this upgrades runtime.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_node
PREFIX="$(d1_prefix)"
VER="$(d1_pkg_version)"
PREV=""
if [[ -L "$PREFIX/current" || -d "$PREFIX/current" ]]; then
  PREV="$(readlink "$PREFIX/current" 2>/dev/null || true)"
fi

# Snapshot pointer for rollback
mkdir -p "$PREFIX"
echo "${PREV:-}" >"$PREFIX/.previous_current"
echo "$VER" >"$PREFIX/.pending_version"

VER_DIR="$PREFIX/versions/$VER"
echo "Pi D1 upgrade → $VER_DIR (was: ${PREV:-none})"
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER" "$PREFIX/current"

# Refresh wrapper if missing
if [[ ! -x "$PREFIX/bin/aiplat-http" ]]; then
  bash "$SCRIPT_DIR/d1_install.sh"
else
  python3 - <<PY
import json, pathlib, datetime
p = pathlib.Path("$PREFIX") / "INSTALL_META.json"
meta = {}
if p.exists():
    meta = json.loads(p.read_text())
meta.update({
  "capability_id": "pi",
  "version": "$VER",
  "prefix": "$PREFIX",
  "upgraded_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
  "previous": "$PREV",
  "thin": True,
})
p.write_text(json.dumps(meta, indent=2) + "\n")
PY
fi

echo "PASS: Pi D1 upgrade current=versions/$VER previous=${PREV:-none}"
echo "Hint: bundle rollback = flip $PREFIX/bundles/current (see GATE3_PI_THIN_ROLLBACK_DRILL.md)"
