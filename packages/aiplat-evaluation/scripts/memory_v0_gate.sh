#!/usr/bin/env bash
# P2-2 persistent memory v0 gate. accuracy_claim=false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_MEMORY_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
PACK="${AIPLAT_EVAL_MEMORY_PACK_V0:-$ROOT/docs/a3/memory_tasks.v0.json}"
mkdir -p "$EVID_DIR"
export AIPLAT_EVAL_MEMORY_EVIDENCE_DIR="$EVID_DIR"
export AIPLAT_EVAL_MEMORY_PACK="$PACK"
export AIPLAT_EVAL_MEMORY_STAMP="$STAMP"

echo "== unit: memory_persist v0 =="
PYTHONPATH=. python3 -m pytest tests/test_memory_persist_v0.py -q --tb=line

echo "== pack execute v0 =="
PYTHONPATH=. python3 - <<'PY'
import json, os
from pathlib import Path
from app.worker.runners import execute_runner

pack = json.loads(Path(os.environ["AIPLAT_EVAL_MEMORY_PACK"]).read_text(encoding="utf-8"))
assert pack.get("accuracy_claim") is False
cases = pack.get("cases") or []
assert len(cases) >= 6
out = execute_runner(
    {
        "job_id": "memory-pack-v0",
        "runner_id": "memory_persist",
        "payload": {"pack_id": pack.get("schema"), "cases": cases},
    }
)
assert out.get("accuracy_claim") is False
evid = out.get("evidence") or {}
dim = evid.get("memory_dimension") or {}
assert dim.get("schema") == "eval.scoring.memory_persist.v0"
assert dim.get("memory_pass") is True, dim
assert not dim.get("kinds_missing"), dim

stamp = os.environ.get("AIPLAT_EVAL_MEMORY_STAMP") or ""
path = Path(os.environ["AIPLAT_EVAL_MEMORY_EVIDENCE_DIR"]) / f"local-eval-memory-v0-gate-{stamp}.json"
payload = {
    "schema": "eval.memory_persist.v0.gate",
    "product_id": "evaluation",
    "environment": "local",
    "accuracy_claim": False,
    "process_split_authorized": False,
    "cases_n": dim.get("cases_n"),
    "case_pass_rate": dim.get("case_pass_rate"),
    "memory_pass": True,
    "kinds_seen": dim.get("kinds_seen"),
    "honesty": "memory_persist v0 fixture store only; not production MemoryManager; not accuracy",
    "recorded_at": stamp,
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "accuracy_claim": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "memory_persist v0 gate PASS (authorize=false)"
