#!/usr/bin/env bash
# P2-1 context management v0 gate. accuracy_claim=false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_CONTEXT_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
PACK="${AIPLAT_EVAL_CONTEXT_PACK_V0:-$ROOT/docs/a3/context_tasks.v0.json}"
mkdir -p "$EVID_DIR"
export AIPLAT_EVAL_CONTEXT_EVIDENCE_DIR="$EVID_DIR"
export AIPLAT_EVAL_CONTEXT_PACK="$PACK"
export AIPLAT_EVAL_CONTEXT_STAMP="$STAMP"

echo "== unit: context_mgmt v0 =="
PYTHONPATH=. python3 -m pytest tests/test_context_mgmt_v0.py -q --tb=line

echo "== pack execute v0 =="
PYTHONPATH=. python3 - <<'PY'
import json, os
from pathlib import Path
from app.worker.runners import execute_runner

pack = json.loads(Path(os.environ["AIPLAT_EVAL_CONTEXT_PACK"]).read_text(encoding="utf-8"))
assert pack.get("accuracy_claim") is False
cases = pack.get("cases") or []
assert len(cases) >= 4
out = execute_runner(
    {
        "job_id": "context-pack-v0",
        "runner_id": "context_mgmt",
        "payload": {"pack_id": pack.get("schema"), "cases": cases},
    }
)
assert out.get("accuracy_claim") is False
evid = out.get("evidence") or {}
dim = evid.get("context_dimension") or {}
assert dim.get("schema") == "eval.scoring.context_mgmt.v0"
assert dim.get("context_pass") is True, dim
assert not dim.get("kinds_missing"), dim

stamp = os.environ.get("AIPLAT_EVAL_CONTEXT_STAMP") or ""
path = Path(os.environ["AIPLAT_EVAL_CONTEXT_EVIDENCE_DIR"]) / f"local-eval-context-v0-gate-{stamp}.json"
payload = {
    "schema": "eval.context_mgmt.v0.gate",
    "product_id": "evaluation",
    "environment": "local",
    "accuracy_claim": False,
    "process_split_authorized": False,
    "cases_n": dim.get("cases_n"),
    "case_pass_rate": dim.get("case_pass_rate"),
    "context_pass": True,
    "kinds_seen": dim.get("kinds_seen"),
    "honesty": "context_mgmt v0 fixtures only; not Session substitute; not G2b; not memory",
    "recorded_at": stamp,
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "accuracy_claim": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "context_mgmt v0 gate PASS (authorize=false)"
