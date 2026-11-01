#!/usr/bin/env bash
# Bring up local-staging compose (PG16 + Keycloak) and run honest local rehearsals.
# environment=local evidence only — never production_signed / cutover_authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
COMPOSE="$ROOT/packages/aiplat-central/compose.local-staging.yml"
CMD="${1:-up}"

usage() {
  cat <<EOF
Usage: $0 [up|down|status|rehearse|oidc|all]
  up       docker compose up -d (PG :5433 + Keycloak :8081)
  down     docker compose down
  status   compose ps + authorize status (expect not ready)
  oidc     Keycloak realm/client/user + CONFIGURE_TOTP (local only)
  rehearse pg_ha_local_rehearsal + ha_failover + oidc + record local-*.json
  all      up → wait → rehearse
EOF
}

need_docker() {
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "ERROR: docker daemon required for local-staging" >&2
    exit 2
  fi
}

compose() {
  docker compose -f "$COMPOSE" "$@"
}

wait_pg() {
  local i
  for i in $(seq 1 40); do
    if docker exec aiplat-local-pg pg_isready -U aiplat -d aiplat_local >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "ERROR: local postgres not ready" >&2
  return 1
}

wait_keycloak() {
  local i
  for i in $(seq 1 60); do
    if curl -sf -o /dev/null "http://127.0.0.1:8081/" 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "WARN: Keycloak :8081 not ready after wait (OIDC may fail; local_signed may stay false)" >&2
  return 1
}

case "$CMD" in
  -h|--help) usage; exit 0 ;;
  up)
    need_docker
    compose up -d
    wait_pg
    echo "PASS: local-staging up"
    echo "  AIPLAT_PG_DSN=postgresql://aiplat:aiplat_local@127.0.0.1:5433/aiplat_local"
    echo "  AIPLAT_OIDC_ISSUER=http://127.0.0.1:8081/realms/aiplat-local  # create realm in Keycloak UI"
    echo "NOTE: environment=local only; cutover_authorized stays false"
    ;;
  down)
    need_docker
    compose down
    echo "PASS: local-staging down"
    ;;
  status)
    need_docker
    compose ps || true
    bash "$ROOT/packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh" status | head -40
    ;;
  oidc)
    need_docker
    bash "$ROOT/packages/aiplat-central/scripts/pg_ha_local_oidc_setup.sh"
    ;;
  rehearse)
    export AIPLAT_PG_DSN="${AIPLAT_PG_DSN:-postgresql://aiplat:aiplat_local@127.0.0.1:5433/aiplat_local}"
    echo "== local SQLite + optional PG schema rehearsal =="
    bash "$ROOT/packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh"
    echo "== docker HA failover rehearsal (ephemeral; still local) =="
    bash "$ROOT/packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh"
    echo "== local OIDC (Keycloak realm + CONFIGURE_TOTP) =="
    OIDC_EVIDENCE=""
    if bash "$ROOT/packages/aiplat-central/scripts/pg_ha_local_oidc_setup.sh"; then
      OIDC_EVIDENCE="$(ls -1t "$ROOT/packages/aiplat-central/docs/pg_ha/drills"/oidc-local-*.json 2>/dev/null | head -1 || true)"
    fi
    echo "== record local-*.json (not live-*.json) =="
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    ITEMS="$(mktemp)"
    if [[ -n "$OIDC_EVIDENCE" && -f "$OIDC_EVIDENCE" ]]; then
      OIDC_DONE=true
      OIDC_EV="pg_ha_local_oidc_setup → $(basename "$OIDC_EVIDENCE") (local; CONFIGURE_TOTP required; not production MFA E2E)"
      LOCAL_SIGN=1
    else
      OIDC_DONE=false
      OIDC_EV=""
      LOCAL_SIGN=0
    fi
    cat >"$ITEMS" <<JSON
{
  "pg_migration": {"done": true, "evidence": "pg_ha_local_rehearsal PG schema via AIPLAT_PG_DSN=$AIPLAT_PG_DSN (local)"},
  "backup_restore": {"done": true, "evidence": "sqlite-rehearsal + optional pg_dump/restore under docs/pg_ha/drills (local)"},
  "ha_failover": {"done": true, "evidence": "pg_ha_ha_failover_rehearsal docker primary/standby dump-promote (local; no VIP)"},
  "rollback": {"done": true, "evidence": "sqlite/pg schema rollback path in local rehearsal (local)"},
  "oidc_full": {"done": $OIDC_DONE, "evidence": "$OIDC_EV"}
}
JSON
    export AIPLAT_LOCAL_DRILL_ID="pgha-local-${STAMP}"
    export AIPLAT_LOCAL_DRILL_OPERATOR="${USER:-ops}"
    export AIPLAT_LOCAL_DRILL_ITEMS_FILE="$ITEMS"
    export AIPLAT_LOCAL_SIGN="$LOCAL_SIGN"
    bash "$ROOT/packages/aiplat-central/scripts/pg_ha_record_local_drill.sh"
    rm -f "$ITEMS"
    echo "NOTE: do NOT flip checklist 🟨→✅; do NOT authorize (local_signed ≠ production_signed)"
    bash "$ROOT/packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh" status >/dev/null
    echo "PASS: local-staging rehearse (cutover still unauthorized)"
    ;;
  all)
    bash "$0" up
    wait_keycloak || true
    bash "$0" rehearse
    ;;
  *)
    usage
    exit 2
    ;;
esac
