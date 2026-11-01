#!/usr/bin/env bash
# Option B (local VM/Docker) — full-track engineering rehearsal.
# environment=local only. Never flips staging_ready / checklist / authorize.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DECISION="$ROOT/reports/five-products/ops/OPTION_B_LOCAL_VM.md"
CLOSEOUT="$ROOT/reports/five-products/ops/ENGINEERING_LOCAL_CLOSEOUT.md"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== Option B all-tracks (local VM/Docker; does NOT authorize) =="
echo "stamp=$STAMP"
[[ -f "$DECISION" ]] || fail "missing $DECISION"

PGHA_MODE="docker"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  export AIPLAT_LOCAL_INCLUDE_PGHA=1
  bash scripts/ops_local_rehearse_tracks.sh || fail "ops_local_rehearse_tracks (with PGHA docker)"
else
  PGHA_MODE="sqlite-fallback-docker-down"
  echo "WARN: docker daemon unavailable — PG/HA uses sqlite/file rehearsal (still environment=local)"
  export AIPLAT_LOCAL_INCLUDE_PGHA=0
  bash scripts/ops_local_rehearse_tracks.sh || fail "ops_local_rehearse_tracks"
  bash packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh || fail "pg_ha_local_rehearsal"
  bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh || fail "pg_ha_ha_failover_rehearsal"
  echo "WARN: restart Docker Desktop then re-run for full PG:5433 + Keycloak:8081"
fi

# 2) Pi D1 / D2 (no staging dependency)
bash packages/aiplat-pi-runtime/scripts/d1_local_regression.sh || fail "pi d1_local_regression"
bash packages/aiplat-pi-runtime/scripts/d2_admin_check.sh || fail "pi d2_admin_check"

# 3) FDE Field local install/meta/backup/rollback
bash packages/aiplat-fde/scripts/d1_local_regression.sh || fail "fde d1_local_regression"

# 3b) aiPlat Central D2 Thin (compat/security/N-1; cutover stays false)
bash packages/aiplat-central/scripts/d2_local_closeout.sh || fail "aiplat d2_local_closeout"

# 4) STATUS↔manifest honesty
"$PY" scripts/check_five_products_status_sync.py || fail "STATUS sync"

# 5) Hard gates still false
bash scripts/ops_live_status.sh --json | "$PY" -c '
import sys, json
d=json.load(sys.stdin)
for t in d["tracks"]:
    assert t.get("ready_to_authorize") is False, t
    assert t.get("authorized") is False, t
print("PASS: all tracks ready_to_authorize=false authorized=false")
'

# 6) Last-run note
NOTE="$ROOT/reports/five-products/ops/OPTION_B_LAST_RUN.md"
cat >"$NOTE" <<EOF
# Option B last full run

- recorded_at: \`$STAMP\`
- command: \`bash scripts/ops_option_b_all.sh\`
- result: **PASS**
- pgha_mode: \`$PGHA_MODE\`
- environment: \`local\`
- staging_ready: **false**
- production_signed: **false**
- authorize: **not attempted**
- decision: [\`OPTION_B_LOCAL_VM.md\`](./OPTION_B_LOCAL_VM.md)
- tracks runlog: [\`LOCAL_TRACKS_RUNLOG.md\`](./LOCAL_TRACKS_RUNLOG.md)
- closeout: [\`ENGINEERING_LOCAL_CLOSEOUT.md\`](./ENGINEERING_LOCAL_CLOSEOUT.md)

## Notes

- Prefer \`pgha_mode=docker\` (PG :5433 + Keycloak :8081).
- If docker down: sqlite/file rehearsal still counts as Option B engineering; re-run after daemon up for full stack.
- Prior docker PASS sample: \`evidence/local-pgha-local-20261031T235626Z.json\`.
EOF

pass "ops_option_b_all ($STAMP) pgha_mode=$PGHA_MODE"
echo "NOTE: Option B engineering only — do not buy server; do not flip hard gates."
