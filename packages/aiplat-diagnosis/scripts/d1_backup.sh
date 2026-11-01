#!/usr/bin/env bash
# Diagnosis D1 backup — tarball of current pointer + optional env + INSTALL_META.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

PREFIX="$(d1_prefix)"
mkdir -p "$PREFIX/backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PREFIX/backups/diagnosis-d1-$stamp.tgz"
args=(current INSTALL_META.json)
[[ -e "$PREFIX/env" ]] && args+=(env)
tar -C "$PREFIX" -czf "$OUT" "${args[@]}"
echo "OK backup → $OUT"
