#!/usr/bin/env bash
# Local chaos / backup-restore drills (SQLite always; optional B4-S Docker kill/restart).
# environment=local ONLY. NEVER sets process_split_authorized=true.
# ≠ staging · ≠ PITR cert · accuracy_claim=false
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_CHAOS_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
AGG_OUT="${AIPLAT_EVAL_CHAOS_AGGREGATE:-$ROOT/docs/a3/evidence/local_chaos_aggregate.v1.json}"
WORK="${AIPLAT_EVAL_CHAOS_WORK:-$(mktemp -d /tmp/aiplat-eval-chaos.XXXXXX)}"
MODE="${AIPLAT_EVAL_CHAOS_MODE:-sqlite}"  # sqlite | b4s | both
mkdir -p "$EVID_DIR" "$WORK" "$(dirname "$AGG_OUT")"

echo "== local chaos drill mode=$MODE work=$WORK =="

SQLITE_OUT="$WORK/sqlite_chaos.json"
python3 "$ROOT/scripts/local_chaos_sqlite.py" --work "$WORK/sqlite" --out "$SQLITE_OUT"
SQLITE_OK="$(python3 -c "import json; print('1' if json.load(open('$SQLITE_OUT'))['gate_ok'] else '0')")"

B4S_OK="skip"
B4S_PAYLOAD="{}"
if [[ "$MODE" == "b4s" || "$MODE" == "both" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "REFUSE: docker required for b4s chaos mode" >&2
    exit 2
  fi
  COMPOSE_FILE="${AIPLAT_EVAL_B4S_COMPOSE:-$ROOT/compose/docker-compose.b4s-local.yml}"
  COMPOSE=(docker compose -f "$COMPOSE_FILE")
  _pg() { "${COMPOSE[@]}" exec -T postgres "$@"; }

  echo "== b4s chaos: compose up postgres =="
  "${COMPOSE[@]}" up -d postgres || { echo "REFUSE: docker compose up failed" >&2; exit 2; }
  for i in $(seq 1 60); do
    if _pg pg_isready -U eval -d eval >/dev/null 2>&1; then break; fi
    sleep 2
    if [[ "$i" -eq 60 ]]; then echo "REFUSE: postgres not ready" >&2; exit 2; fi
  done

  export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-postgresql://eval:eval_local@127.0.0.1:5434/eval}"
  bash "$ROOT/scripts/migrate_local.sh"

  PYTHONPATH=. python3 - <<'PY'
import os
from app.store.jobs import enqueue_job
enqueue_job(
    os.environ["AIPLAT_EVAL_DB_URL"],
    runner_id="prompt_eval",
    tenant_id="chaos-local",
    payload={"prompt": "chaos-seed", "expected": ""},
)
print("seeded")
PY

  BACKUP="$WORK/eval_backup.sql"
  _pg pg_dump -U eval eval > "$BACKUP"
  test -s "$BACKUP"
  BEFORE="$(_pg psql -U eval -d eval -tAc "SELECT count(*) FROM eval_jobs;" | tr -d '[:space:]')"
  test "${BEFORE}" -ge 1

  echo "== b4s chaos: kill postgres + restart =="
  "${COMPOSE[@]}" kill postgres || true
  "${COMPOSE[@]}" up -d postgres
  for i in $(seq 1 60); do
    if _pg pg_isready -U eval -d eval >/dev/null 2>&1; then break; fi
    sleep 2
    if [[ "$i" -eq 60 ]]; then echo "REFUSE: postgres not ready after kill" >&2; exit 2; fi
  done
  AFTER_KILL="$(_pg psql -U eval -d eval -tAc "SELECT count(*) FROM eval_jobs;" | tr -d '[:space:]' || echo 0)"
  # Volume usually survives kill; if empty, restore from backup.
  if [[ "${AFTER_KILL}" != "${BEFORE}" ]]; then
    echo "== rows missing after kill ($AFTER_KILL vs $BEFORE); restore =="
    _pg psql -U eval -d eval -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    _pg psql -U eval -d eval < "$BACKUP"
    AFTER_KILL="$(_pg psql -U eval -d eval -tAc "SELECT count(*) FROM eval_jobs;" | tr -d '[:space:]')"
  fi
  test "$AFTER_KILL" = "$BEFORE"

  echo "== b4s chaos: intentional wipe + restore =="
  _pg psql -U eval -d eval -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
  _pg psql -U eval -d eval < "$BACKUP"
  AFTER_RESTORE="$(_pg psql -U eval -d eval -tAc "SELECT count(*) FROM eval_jobs;" | tr -d '[:space:]')"
  test "$AFTER_RESTORE" = "$BEFORE"

  B4S_OK="1"
  B4S_PAYLOAD=$(python3 - <<PY
import json
print(json.dumps({
  "id": "b4s_kill_restart_wipe_restore",
  "ok": True,
  "jobs_before": int("${BEFORE}"),
  "jobs_after_kill": int("${AFTER_KILL}"),
  "jobs_after_wipe_restore": int("${AFTER_RESTORE}"),
  "backup_bytes": $(wc -c < "$BACKUP" | tr -d ' '),
}))
PY
)
fi

echo "== authorize must stay false =="
STATUS_JSON="$(bash "$ROOT/scripts/a3_split_authorize.sh" status)"
echo "$STATUS_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('ready_to_authorize') is False
assert d.get('process_split_authorized_doc') is False
print('authorize still locked')
"

DRILL="$EVID_DIR/local-eval-chaos-${STAMP}.json"
export AIPLAT_CHAOS_SQLITE_OUT="$SQLITE_OUT"
export AIPLAT_CHAOS_SQLITE_OK="$SQLITE_OK"
export AIPLAT_CHAOS_B4S_OK="$B4S_OK"
export AIPLAT_CHAOS_B4S_PAYLOAD="$B4S_PAYLOAD"
export AIPLAT_CHAOS_MODE="$MODE"
export AIPLAT_CHAOS_STAMP="$STAMP"
export AIPLAT_CHAOS_DRILL="$DRILL"
export AIPLAT_CHAOS_AGG="$AGG_OUT"

python3 - <<'PY'
import json, os
from pathlib import Path

sqlite = json.loads(Path(os.environ["AIPLAT_CHAOS_SQLITE_OUT"]).read_text(encoding="utf-8"))
b4s_ok = os.environ["AIPLAT_CHAOS_B4S_OK"]
scenarios = list(sqlite.get("scenarios") or [])
if b4s_ok == "1":
    scenarios.append(json.loads(os.environ["AIPLAT_CHAOS_B4S_PAYLOAD"]))
gate = bool(sqlite.get("gate_ok")) and b4s_ok in ("1", "skip")
if os.environ["AIPLAT_CHAOS_MODE"] in ("b4s", "both") and b4s_ok != "1":
    gate = False

payload = {
    "schema": "eval.local_chaos.drill.v1",
    "product_id": "evaluation",
    "environment": "local",
    "mode": os.environ["AIPLAT_CHAOS_MODE"],
    "accuracy_claim": False,
    "not_accuracy_certification": True,
    "not_staging_evidence": True,
    "process_split_authorized": False,
    "gate_ok": gate,
    "sqlite_ok": bool(int(os.environ["AIPLAT_CHAOS_SQLITE_OK"])),
    "b4s_ok": b4s_ok,
    "scenarios": scenarios,
    "honesty": (
        "local chaos backup/restore — kill/restart + wipe/restore; "
        "≠ staging; ≠ PITR; ≠ process_split; accuracy_claim=false"
    ),
    "recorded_at": os.environ["AIPLAT_CHAOS_STAMP"],
}
drill = Path(os.environ["AIPLAT_CHAOS_DRILL"])
drill.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

agg = {
    "schema": "eval.local_chaos.aggregate.v1",
    "product_id": "evaluation",
    "environment": "local",
    "accuracy_claim": False,
    "not_accuracy_certification": True,
    "not_staging_evidence": True,
    "process_split_authorized": False,
    "gate_ok": gate,
    "mode": payload["mode"],
    "scenarios_ok": sum(1 for s in scenarios if s.get("ok")),
    "scenarios_n": len(scenarios),
    "source_drill": f"docs/a3/drills/{drill.name}",
    "honesty": payload["honesty"],
    "recorded_at": payload["recorded_at"],
}
Path(os.environ["AIPLAT_CHAOS_AGG"]).write_text(
    json.dumps(agg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({
    "gate": "ok" if gate else "fail",
    "drill": str(drill),
    "aggregate": os.environ["AIPLAT_CHAOS_AGG"],
    "scenarios_ok": agg["scenarios_ok"],
    "accuracy_claim": False,
    "process_split_authorized": False,
}, ensure_ascii=False))
raise SystemExit(0 if gate else 1)
PY
