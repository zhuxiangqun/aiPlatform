#!/usr/bin/env bash
# Central D1 upgrade — rematerialize current package version under prefix.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_python
PREFIX="$(d1_prefix)"
VER="$(d1_pkg_version)"
VER_DIR="$PREFIX/versions/$VER"
mkdir -p "$PREFIX/versions" "$PREFIX/backups"

# backup current pointer target if any
if [[ -L "$PREFIX/current" || -d "$PREFIX/current" ]]; then
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$PREFIX/backups"
  tar -C "$PREFIX" -czf "$PREFIX/backups/pre-upgrade-$stamp.tgz" current env INSTALL_META.json 2>/dev/null || true
fi

echo "Upgrade → $VER_DIR"
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER" "$PREFIX/current"
cat >"$PREFIX/INSTALL_META.json" <<EOF
{"capability_id":"aiplat","product_id":"aiplat","deploy_unit":"central","version":"$VER","prefix":"$PREFIX","upgraded_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","thin":true,"pg_ha":false}
EOF
echo "OK upgraded Central Thin → $PREFIX/current"
