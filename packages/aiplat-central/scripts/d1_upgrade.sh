#!/usr/bin/env bash
# Central D1/D2 upgrade — distinct version slot for runtime rollback.
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
mkdir -p "$PREFIX" "$PREFIX/versions" "$PREFIX/backups"
echo "${PREV:-}" >"$PREFIX/.previous_current"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tar -C "$PREFIX" -czf "$PREFIX/backups/pre-upgrade-$stamp.tgz" current env INSTALL_META.json 2>/dev/null || true

VER_SLOT="$VER"
VER_DIR="$PREFIX/versions/$VER_SLOT"
if [[ -d "$VER_DIR" ]]; then
  VER_SLOT="${VER}+${stamp}"
  VER_DIR="$PREFIX/versions/$VER_SLOT"
fi
echo "Central upgrade → $VER_DIR (was: ${PREV:-none})"
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER_SLOT" "$PREFIX/current"
cat >"$PREFIX/INSTALL_META.json" <<EOF
{"capability_id":"aiplat","product_id":"aiplat","deploy_unit":"central","version":"$VER","version_slot":"$VER_SLOT","prefix":"$PREFIX","upgraded_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","previous":"$PREV","thin":true,"pg_ha":false,"d2_thin_pack":true}
EOF
echo "PASS: Central upgrade current=versions/$VER_SLOT"
