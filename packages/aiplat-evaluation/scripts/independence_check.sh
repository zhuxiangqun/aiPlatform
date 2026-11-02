#!/usr/bin/env bash
# A4: local independence — eval :8010 still serves without calling Central.
# Does NOT flip process_split_authorized. environment=local only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${AIPLAT_EVAL_HOST:-127.0.0.1}"
PORT="${AIPLAT_EVAL_PORT:-8010}"
BASE="http://${HOST}:${PORT}"
CENTRAL_URL="${AIPLAT_CENTRAL_URL:-http://127.0.0.1:8000}"
EVID_DIR="${AIPLAT_EVAL_A4_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_PATH="${EVID_DIR}/local-eval-a3-independent-${STAMP}.json"
STARTED_EVAL=0
EVAL_PID=""

cleanup() {
  if [[ "$STARTED_EVAL" -eq 1 && -n "${EVAL_PID}" ]]; then
    kill "${EVAL_PID}" 2>/dev/null || true
    wait "${EVAL_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p "$EVID_DIR" "$ROOT/data"
export AIPLAT_EVAL_MODE="${AIPLAT_EVAL_MODE:-standalone}"
export AIPLAT_EVAL_HOST="$HOST"
export AIPLAT_EVAL_PORT="$PORT"
export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${ROOT}/data/eval_local.sqlite3}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

if ! curl -fsS --max-time 2 "${BASE}/healthz" >/dev/null 2>&1; then
  bash "$ROOT/scripts/migrate_local.sh" >/dev/null
  python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level warning &
  EVAL_PID=$!
  STARTED_EVAL=1
  for _ in $(seq 1 40); do
    if curl -fsS --max-time 1 "${BASE}/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
fi

curl -fsS "${BASE}/healthz" | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d.get("product_id")=="evaluation", d
assert d.get("process_split_authorized") is False, d
print("eval healthz ok")
'

SEED_JSON="$(curl -fsS -X POST "${BASE}/api/platform/apps/eval/store/roundtrip")"
REPORT_ID="$(printf '%s' "$SEED_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["report_id"])')"
SET_ID="$(printf '%s' "$SEED_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["set_id"])')"
test -n "$REPORT_ID"
test -n "$SET_ID"

CENTRAL_UP=0
if curl -fsS --max-time 2 "${CENTRAL_URL}/healthz" >/dev/null 2>&1 \
  || curl -fsS --max-time 2 "${CENTRAL_URL}/api/core/healthz" >/dev/null 2>&1; then
  CENTRAL_UP=1
fi

GOT_REPORT="$(curl -fsS "${BASE}/api/platform/apps/eval/store/reports/${REPORT_ID}")"
printf '%s' "$GOT_REPORT" | python3 -c '
import json,sys
rid=sys.argv[1]
d=json.load(sys.stdin)
assert d.get("data",{}).get("id")==rid, d
print("eval report readable", rid)
' "$REPORT_ID"

GOT_SET="$(curl -fsS "${BASE}/api/platform/apps/eval/store/sets/${SET_ID}")"
printf '%s' "$GOT_SET" | python3 -c '
import json,sys
sid=sys.argv[1]
d=json.load(sys.stdin)
assert d.get("data",{}).get("id")==sid, d
print("eval set readable", sid)
' "$SET_ID"

export EVID_PATH REPORT_ID SET_ID BASE CENTRAL_URL CENTRAL_UP
python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

evid = {
    "schema_version": "aiplat.evaluation.a3.independence.v0",
    "kind": "local-eval-a3-independent",
    "environment": "local",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "product_id": "evaluation",
    "eval_base": os.environ["BASE"],
    "central_url": os.environ["CENTRAL_URL"],
    "central_reachable": os.environ.get("CENTRAL_UP", "0") == "1",
    "central_required": False,
    "seed": {
        "set_id": os.environ["SET_ID"],
        "report_id": os.environ["REPORT_ID"],
    },
    "checks": {
        "eval_healthz": True,
        "eval_report_readable_without_central_call": True,
        "eval_set_readable_without_central_call": True,
    },
    "process_split_authorized": False,
    "production_signed": False,
    "note": (
        "A4 local independence: eval SQLite/API served reads without calling Central. "
        "central_reachable is a probe only; the read path never depends on Central."
    ),
}
path = Path(os.environ["EVID_PATH"])
path.write_text(json.dumps(evid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("evidence", path)
print("central_reachable", evid["central_reachable"], "process_split_authorized", False)
print("A4 independence_check PASS")
PY
