#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"
PREFIX="$(d1_prefix)"
mkdir -p "$PREFIX/backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PREFIX/backups/fde-d1-prep-$stamp.tgz"
tar -C "$PREFIX" -czf "$OUT" current env INSTALL_META.json data 2>/dev/null \
  || tar -C "$PREFIX" -czf "$OUT" .
echo "OK backup → $OUT"
