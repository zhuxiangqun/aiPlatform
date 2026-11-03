#!/usr/bin/env bash
# Multi-turn session_eval v1 gate (5–8 turns). accuracy_claim=false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_SESSION_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
PACK="${AIPLAT_EVAL_SESSION_PACK_V1:-$ROOT/docs/a3/session_tasks.v1.json}"
mkdir -p "$EVID_DIR"
export AIPLAT_EVAL_SESSION_EVIDENCE_DIR="$EVID_DIR"
export AIPLAT_EVAL_SESSION_PACK="$PACK"
export AIPLAT_EVAL_SESSION_STAMP="$STAMP"

echo "== unit: session_eval v0+v1 =="
PYTHONPATH=. python3 -m pytest \
  tests/test_session_eval_v0.py \
  tests/test_session_eval_v1.py -q --tb=line

echo "== pack execute v1 =="
PYTHONPATH=. python3 - <<'PY'
import json, os
from pathlib import Path
from app.worker.runners import execute_runner

pack = json.loads(Path(os.environ["AIPLAT_EVAL_SESSION_PACK"]).read_text(encoding="utf-8"))
sessions = pack.get("sessions") or []
assert len(sessions) >= 2
rows = []
for sess in sessions:
    out = execute_runner(
        {
            "job_id": str(sess.get("session_id") or "sess"),
            "runner_id": "session_eval",
            "payload": sess,
        }
    )
    assert out.get("accuracy_claim") is False
    sdim = (out.get("scoring") or {}).get("dimensions", {}).get("session") or {}
    assert sdim.get("profile") == "v1"
    assert 5 <= int(sdim.get("turns_n") or 0) <= 8
    rows.append(
        {
            "session_id": sess.get("session_id"),
            "ok": out.get("ok"),
            "turn_success_rate": (out.get("metrics") or {}).get("turn_success_rate"),
            "session_dimension": sdim,
        }
    )

stamp = os.environ.get("AIPLAT_EVAL_SESSION_STAMP") or ""
evid = Path(os.environ["AIPLAT_EVAL_SESSION_EVIDENCE_DIR"])
payload = {
    "schema": "eval.session.v1.gate",
    "product_id": "evaluation",
    "environment": "local",
    "accuracy_claim": False,
    "process_split_authorized": False,
    "sessions_n": len(rows),
    "all_ok": all(bool(r.get("ok")) for r in rows),
    "sessions": rows,
    "honesty": "multi-turn v1 only (5–8 turns); not full dialogue; not G2b accuracy",
    "recorded_at": stamp,
}
path = evid / f"local-eval-session-v1-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
assert payload["all_ok"] is True, rows
print(json.dumps({"gate": "ok", "evidence": str(path), "accuracy_claim": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "session_eval v1 gate PASS (authorize=false)"
