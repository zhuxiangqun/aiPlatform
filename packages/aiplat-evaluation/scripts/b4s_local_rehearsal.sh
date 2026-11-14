#!/usr/bin/env bash
# B4-S local rehearsal — PG backup/restore + dual-read (+ optional MinIO/Keycloak).
# environment=local ONLY. NEVER sets process_split_authorized=true.
# NEVER claims staging evidence.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

PY="${AIPLAT_EVAL_PYTHON:-python3}"
[[ -x "$REPO_ROOT/.venv/bin/python" ]] && PY="$REPO_ROOT/.venv/bin/python"
export AIPLAT_EVAL_PYTHON="$PY"

COMPOSE_FILE="${AIPLAT_EVAL_B4S_COMPOSE:-$ROOT/compose/docker-compose.b4s-local.yml}"
COMPOSE=(docker compose -f "$COMPOSE_FILE")
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_B4S_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
WORK="${AIPLAT_EVAL_B4S_WORK:-$(mktemp -d /tmp/aiplat-eval-b4s.XXXXXX)}"
mkdir -p "$EVID_DIR" "$WORK"
SKIP_KC="${AIPLAT_EVAL_B4S_SKIP_KEYCLOAK:-1}"
SKIP_MINIO="${AIPLAT_EVAL_B4S_SKIP_MINIO:-1}"

echo "== B4-S local rehearsal workdir=$WORK =="

if ! command -v docker >/dev/null 2>&1; then
  echo "REFUSE: docker required for B4-S local rehearsal" >&2
  exit 2
fi

_pg_exec() {
  local bin="$1"; shift
  "${COMPOSE[@]}" exec -T postgres "$bin" "$@"
}

echo "== compose up dedicated b4s postgres on :5434 (does not touch :5433 aiplat_local) =="
UP_ARGS=(up -d postgres)
if [[ "$SKIP_MINIO" != "1" ]]; then
  UP_ARGS=(--profile minio "${UP_ARGS[@]}" minio)
fi
if [[ "$SKIP_KC" != "1" ]]; then
  UP_ARGS=(--profile keycloak "${UP_ARGS[@]}" keycloak)
fi
"${COMPOSE[@]}" "${UP_ARGS[@]}"

echo "== wait postgres =="
for i in $(seq 1 60); do
  if _pg_exec pg_isready -U eval -d eval >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "REFUSE: postgres not ready" >&2
    exit 2
  fi
done

export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-postgresql://eval:eval_local@127.0.0.1:5434/eval}"

echo "== migrate_local =="
bash "$ROOT/scripts/migrate_local.sh"

echo "== seed one job row =="
SEED_JOB="$WORK/seed_job_id.txt"
PYTHONPATH=. "$PY" - <<PY
import os
from app.store.jobs import enqueue_job
url = os.environ["AIPLAT_EVAL_DB_URL"]
job = enqueue_job(
    url,
    runner_id="prompt_eval",
    tenant_id="b4s-local",
    payload={"prompt": "b4s-seed", "expected": ""},
)
path = "${SEED_JOB}"
open(path, "w", encoding="utf-8").write(str(job["job_id"]))
print("seeded", job["job_id"])
PY

echo "== pg_dump backup =="
BACKUP="$WORK/eval_backup.sql"
_pg_exec pg_dump -U eval eval > "$BACKUP"
test -s "$BACKUP"

BEFORE="$(_pg_exec psql -U eval -d eval -tAc "SELECT count(*) FROM eval_jobs;" | tr -d '[:space:]')"
echo "jobs_before=$BEFORE"
test "${BEFORE}" -ge 1

echo "== destroy schema =="
_pg_exec psql -U eval -d eval -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "== restore =="
_pg_exec psql -U eval -d eval < "$BACKUP"
AFTER="$(_pg_exec psql -U eval -d eval -tAc "SELECT count(*) FROM eval_jobs;" | tr -d '[:space:]')"
echo "jobs_after_restore=$AFTER"
test "$AFTER" = "$BEFORE"

echo "== dual-read drill =="
bash "$ROOT/scripts/b3l_dual_read_drill.sh"

KC_PY=False
echo "== keycloak jwks probe (optional) =="
if curl -fsS --max-time 3 "http://127.0.0.1:8081/realms/master/protocol/openid-connect/certs" >/dev/null 2>&1 \
  || curl -fsS --max-time 3 "http://127.0.0.1:8088/realms/master/protocol/openid-connect/certs" >/dev/null 2>&1; then
  KC_PY=True
  echo "keycloak JWKS reachable"
else
  echo "WARN: keycloak JWKS not reachable; recorded as soft_fail (PG drill still counts)"
fi

echo "== Chart/runtime authorize must stay locked =="
STATUS_JSON="$(bash "$ROOT/scripts/a3_split_authorize.sh" status)"
echo "$STATUS_JSON" | "$PY" -c "
import json,sys
from pathlib import Path
d=json.load(sys.stdin)
assert d.get('ready_to_authorize') is False, d
assert d.get('live_production_signed') is False, d
chart = Path('chart/Chart.yaml').read_text(encoding='utf-8')
assert 'aiplat.a3_process_split_authorized: \"false\"' in chart
print('ready_to_authorize=false; live_production_signed=false; Chart false')
"

"$PY" - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone

payload = {
    "schema": "eval.b4s.local_rehearsal.v0",
    "product_id": "evaluation",
    "environment": "local",
    "not_staging_evidence": True,
    "option_b_track": True,
    "process_split_authorized": False,
    "chart_a3_process_split_authorized": False,
    "production_signed": False,
    "accuracy_claim": False,
    "compose_file": "compose/docker-compose.b4s-local.yml",
    "db_url_host": "127.0.0.1:5434",
    "jobs_before": int("${BEFORE}"),
    "jobs_after_restore": int("${AFTER}"),
    "backup_bytes": Path("${BACKUP}").stat().st_size,
    "dual_read_drill": True,
    "keycloak_jwks_ok": ${KC_PY},
    "skip_keycloak": "${SKIP_KC}" == "1",
    "skip_minio": "${SKIP_MINIO}" == "1",
    "recorded_at": "${STAMP}" or datetime.now(timezone.utc).isoformat(),
    "honesty": (
        "B4-S Option B local Docker rehearsal (:5434 sibling of PGHA :5433) — "
        "not staging host; not PITR certification; Chart/runtime authorize stays false"
    ),
}
path = Path("${EVID_DIR}") / f"local-eval-b4s-rehearsal-${STAMP}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "not_staging_evidence": True}, ensure_ascii=False))
PY

echo "B4-S local rehearsal PASS (authorize=false; not_staging_evidence=true)"
