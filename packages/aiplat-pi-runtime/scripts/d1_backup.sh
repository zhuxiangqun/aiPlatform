#!/usr/bin/env bash
# Pi D1 backup — archive env + current bundle pointer + INSTALL_META (local Thin state).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

PREFIX="$(d1_prefix)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${1:-$PREFIX/backups}"
mkdir -p "$OUT_DIR"
ARCHIVE="$OUT_DIR/pi-d1-backup-$STAMP.tgz"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/pi"
[[ -f "$PREFIX/env" ]] && cp "$PREFIX/env" "$TMP/pi/env"
[[ -f "$PREFIX/INSTALL_META.json" ]] && cp "$PREFIX/INSTALL_META.json" "$TMP/pi/"
[[ -f "$PREFIX/.previous_current" ]] && cp "$PREFIX/.previous_current" "$TMP/pi/"
if [[ -L "$PREFIX/current" ]]; then
  readlink "$PREFIX/current" >"$TMP/pi/current.link"
fi
if [[ -L "$PREFIX/bundles/current" ]]; then
  readlink "$PREFIX/bundles/current" >"$TMP/pi/bundles.current.link"
fi
# Copy resolved bundle (small fixtures OK; large apps: pointer only unless AIPLAT_PI_BACKUP_BUNDLE=1)
if [[ "${AIPLAT_PI_BACKUP_BUNDLE:-0}" == "1" && -d "$PREFIX/bundles/current" ]]; then
  cp -a "$PREFIX/bundles/current" "$TMP/pi/bundle_snapshot"
fi

tar -C "$TMP" -czf "$ARCHIVE" pi
echo "PASS: backup → $ARCHIVE"
echo "$ARCHIVE"
