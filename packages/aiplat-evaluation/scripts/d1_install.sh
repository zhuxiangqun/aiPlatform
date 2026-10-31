#!/usr/bin/env bash
# Evaluation D1 install — materialize co-hosted capability under $AIPLAT_HOME/evaluation.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

SMOKE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) SMOKE=1; shift ;;
    -h|--help) echo "Usage: $0 [--smoke]"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

d1_require_python
PREFIX="$(d1_prefix)"; VER="$(d1_pkg_version)"; VER_DIR="$PREFIX/versions/$VER"
mkdir -p "$PREFIX/versions" "$PREFIX/backups" "$PREFIX/logs"
echo "Evaluation D1 install → $VER_DIR"
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER" "$PREFIX/current"
cat >"$PREFIX/INSTALL_META.json" <<EOF
{"capability_id":"evaluation","product_id":"evaluation","deploy_unit":"central","hosted_by":"aiplat","version":"$VER","prefix":"$PREFIX","installed_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","thin":true,"a3_split":false}
EOF
echo "OK installed Evaluation Thin → $PREFIX/current"
[[ "$SMOKE" -eq 1 ]] && bash "$SCRIPT_DIR/d1_smoke.sh"
