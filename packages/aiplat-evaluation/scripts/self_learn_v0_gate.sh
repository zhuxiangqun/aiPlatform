#!/usr/bin/env bash
# P2-3 self-learn resistance v0 gate. accuracy_claim=false; writeback_authorized=false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_SELF_LEARN_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
PACK="${AIPLAT_EVAL_SELF_LEARN_PACK_V0:-$ROOT/docs/a3/self_learn_tasks.v0.json}"
mkdir -p "$EVID_DIR"
export AIPLAT_EVAL_SELF_LEARN_EVIDENCE_DIR="$EVID_DIR"
export AIPLAT_EVAL_SELF_LEARN_PACK="$PACK"
export AIPLAT_EVAL_SELF_LEARN_STAMP="$STAMP"

echo "== unit: self_learn v0 =="
PYTHONPATH=. python3 -m pytest tests/test_self_learn_v0.py -q --tb=line

echo "== pack execute v0 =="
PYTHONPATH=. python3 - <<'PY'
import json, os
from pathlib import Path
from app.worker.runners import execute_runner

pack = json.loads(Path(os.environ["AIPLAT_EVAL_SELF_LEARN_PACK"]).read_text(encoding="utf-8"))
assert pack.get("accuracy_claim") is False
assert pack.get("writeback_authorized") is False
assert float(pack.get("calibration_disagree_rate") or 0) >= 0.20
cases = pack.get("cases") or []
assert len(cases) >= 5
out = execute_runner(
    {
        "job_id": "self-learn-pack-v0",
        "runner_id": "self_learn",
        "payload": {
            "pack_id": pack.get("schema"),
            "cases": cases,
            "writeback_authorized": pack.get("writeback_authorized"),
            "calibration_disagree_rate": pack.get("calibration_disagree_rate"),
        },
    }
)
assert out.get("accuracy_claim") is False
evid = out.get("evidence") or {}
dim = evid.get("self_learn_dimension") or {}
assert dim.get("schema") == "eval.scoring.self_learn.v0"
assert dim.get("self_learn_pass") is True, dim
assert dim.get("writeback_authorized") is False
assert not dim.get("kinds_missing"), dim

stamp = os.environ.get("AIPLAT_EVAL_SELF_LEARN_STAMP") or ""
path = Path(os.environ["AIPLAT_EVAL_SELF_LEARN_EVIDENCE_DIR"]) / f"local-eval-self-learn-v0-gate-{stamp}.json"
payload = {
    "schema": "eval.self_learn.v0.gate",
    "product_id": "evaluation",
    "environment": "local",
    "accuracy_claim": False,
    "writeback_authorized": False,
    "process_split_authorized": False,
    "calibration_disagree_rate": pack.get("calibration_disagree_rate"),
    "cases_n": dim.get("cases_n"),
    "case_pass_rate": dim.get("case_pass_rate"),
    "self_learn_pass": True,
    "kinds_seen": dim.get("kinds_seen"),
    "honesty": "self_learn v0 resistance fixtures; writeback false; not production learning cert",
    "recorded_at": stamp,
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "writeback_authorized": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "self_learn v0 gate PASS (authorize=false; writeback=false)"
