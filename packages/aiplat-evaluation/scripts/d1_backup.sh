#!/usr/bin/env bash
# Evaluation D1 backup — tarball of current pointer + env + INSTALL_META (cohost Thin).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

PREFIX="$(d1_prefix)"
mkdir -p "$PREFIX/backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PREFIX/backups/evaluation-d1-$stamp.tgz"
tar -C "$PREFIX" -czf "$OUT" current env INSTALL_META.json 2>/dev/null \
  || tar -C "$PREFIX" -czf "$OUT" .
echo "OK backup → $OUT"
