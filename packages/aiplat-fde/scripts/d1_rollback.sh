#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"
PREFIX="$(d1_prefix)"
TARGET_VER=""; BACKUP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) TARGET_VER="$2"; shift 2 ;;
    --backup) BACKUP="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 --version <ver> | --backup <tgz>"; exit 0 ;;
    *) echo "Unknown: $1" >&2; exit 2 ;;
  esac
done
if [[ -n "$BACKUP" ]]; then
  [[ -f "$BACKUP" ]] || { echo "ERROR: missing $BACKUP" >&2; exit 3; }
  tar -C "$PREFIX" -xzf "$BACKUP"
  echo "OK restored $BACKUP"; exit 0
fi
[[ -n "$TARGET_VER" ]] || { echo "ERROR: need --version or --backup" >&2; exit 2; }
[[ -d "$PREFIX/versions/$TARGET_VER" ]] || { echo "ERROR: missing version" >&2; exit 3; }
ln -sfn "versions/$TARGET_VER" "$PREFIX/current"
echo "OK rolled back → versions/$TARGET_VER"
