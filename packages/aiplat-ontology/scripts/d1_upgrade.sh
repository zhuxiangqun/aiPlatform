#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"
PREFIX="$(d1_prefix)"; VER="$(d1_pkg_version)"; VER_DIR="$PREFIX/versions/$VER"
mkdir -p "$PREFIX/versions" "$PREFIX/backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tar -C "$PREFIX" -czf "$PREFIX/backups/pre-upgrade-$stamp.tgz" current INSTALL_META.json 2>/dev/null || true
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER" "$PREFIX/current"
echo "OK upgraded Ontology Thin → $PREFIX/current"
