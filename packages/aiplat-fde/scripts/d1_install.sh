#!/usr/bin/env bash
# FDE Field D1 install — materialize under $AIPLAT_HOME/fde.
# ADR-FDE-FIELD-DEPLOY Accepted (2026-10-30). production_field=true.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

SMOKE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) SMOKE=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--smoke]"
      echo "  Field D1 under \${AIPLAT_FDE_PREFIX:-\$AIPLAT_HOME/fde} (ADR Accepted)"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

d1_require_python
PREFIX="$(d1_prefix)"; VER="$(d1_pkg_version)"; VER_DIR="$PREFIX/versions/$VER"
mkdir -p "$PREFIX/versions" "$PREFIX/backups" "$PREFIX/logs" "$PREFIX/data/projects" "$PREFIX/data/evidence"
echo "FDE Field D1 install → $VER_DIR (ADR Accepted)"
d1_materialize_version "$VER_DIR"
ln -sfn "versions/$VER" "$PREFIX/current"

ENV_FILE="$PREFIX/env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat >"$ENV_FILE" <<EOF
# FDE Field D1 — ADR-FDE-FIELD-DEPLOY Accepted
AIPLAT_FDE_OPTIONAL_SPLIT=0
ADR09_FDE_HEALTH_PORT=18766
ADR09_FDE_HEALTH_HOST=127.0.0.1
AIPLAT_ENTERPRISE=0
EOF
  echo "Wrote $ENV_FILE"
fi

cat >"$PREFIX/INSTALL_META.json" <<EOF
{"capability_id":"fde","product_id":"fde","deploy_unit":"field","version":"$VER","prefix":"$PREFIX","installed_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","thin":true,"field_d1_adr":"accepted","production_field":true,"adr":"reports/five-products/ADR-FDE-FIELD-DEPLOY.md","signoff":"POST /api/platform/apps/fde/acceptance/signoff"}
EOF
echo "OK installed FDE Field D1 → $PREFIX/current (production_field=true)"
[[ "$SMOKE" -eq 1 ]] && bash "$SCRIPT_DIR/d1_smoke.sh"
