#!/usr/bin/env bash
# P1 local gate — scoring semantics; accuracy_claim stays false.
# NEVER sets process_split_authorized=true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_P1_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

PYTHONPATH=. python3 -m pytest \
  tests/test_p1_scoring_semantics.py \
  tests/test_p1_1_kb_arena_metrics.py \
  tests/test_p1_2_gold_replay_metrics.py \
  tests/test_p1_composite_semantics.py \
  tests/test_p1_groundedness_latency.py -q --tb=line

python3 - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone
from app.scoring.semantics import build_scoring_block, prompt_eval_p1_metrics
from app.worker.runners import execute_runner

m = prompt_eval_p1_metrics(
    actual="hi",
    expected="hi",
    context="say hi please",
    exact_match=1.0,
    ok=True,
    llm_audit={"latency_ms": 3, "cost_estimate": 0.0},
)
block = build_scoring_block(m)
assert block["accuracy_claim"] is False
assert block["families"]["accuracy"] == {}
assert "text_quality" in block["families"]["quality"]

out = execute_runner(
    {
        "job_id": "p1-gate",
        "runner_id": "prompt_eval",
        "payload": {"prompt": "x", "expected": "y", "actual": "y", "context": "y z"},
    }
)
assert out["accuracy_claim"] is False
assert out["scoring"]["g2b_unlocked"] is False
assert "accuracy" not in out["metrics"]
comp = out["scoring"]["composite"]
assert comp["accuracy_claim"] is False
assert comp["score"] is not None
assert "text_quality" in comp["scored_metrics"]
assert "content_safety" in comp["scored_metrics"]


stamp = "${STAMP}"
evid = Path("${EVID_DIR}")
payload = {
    "schema": "eval.p1.scoring_gate.v0",
    "product_id": "evaluation",
    "phase": "P1",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "g2b_unlocked": False,
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
    "sample_families": {k: list(v.keys()) for k, v in out["scoring"]["families"].items()},
    "honesty": "P1 scoring semantics only — quality/safety/efficiency are not accuracy",
}
path = evid / f"local-eval-p1-scoring-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "accuracy_claim": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "P1 local scoring gate PASS (accuracy_claim=false)"
