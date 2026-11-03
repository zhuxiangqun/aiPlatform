#!/usr/bin/env bash
# P1 canonical honesty gate — package scored vs Central legacy report-only.
# NEVER sets process_split_authorized=true. accuracy_claim stays false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_P1_CANON_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"

echo "== unit: package P1 composite =="
PYTHONPATH=. python3 -m pytest \
  tests/test_p1_composite_semantics.py \
  tests/test_p1_scoring_semantics.py -q --tb=line

echo "== unit: Central legacy honesty =="
cd "$REPO"
PYTHONPATH=aiPlat-core python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_eval_p1_canonical_honesty.py -q --tb=line

export AIPLAT_EVAL_P1_CANON_STAMP="$STAMP"
export AIPLAT_EVAL_P1_CANON_EVID="$EVID_DIR"
PYTHONPATH=aiPlat-core:"$ROOT" python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

from app.scoring.composite import build_composite, metric_role
from core.harness.evaluation.eval_types import AgentEvalResult

assert metric_role("text_quality") == "scored"
assert metric_role("content_safety") == "scored"
assert metric_role("refusal") == "scored"
assert metric_role("asr") == "report_only"
comp = build_composite({"text_quality": 1.0, "content_safety": 1.0, "asr": 0.0})
assert comp["accuracy_claim"] is False
assert comp["score"] is not None
assert "asr" in (comp.get("report_only_metrics") or {})
h = AgentEvalResult(agent_id="gate").scoring_honesty()
assert h["composite_policy"] == "legacy_7dim"
assert "text_quality" in h["report_only_dimensions"]
assert h["accuracy_claim"] is False

stamp = os.environ["AIPLAT_EVAL_P1_CANON_STAMP"]
evid = Path(os.environ["AIPLAT_EVAL_P1_CANON_EVID"])
payload = {
    "schema": "eval.p1.canonical_gate.v0",
    "product_id": "evaluation",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "package_canonical": "packages/aiplat-evaluation/app/scoring/composite.py",
    "central_policy": h["composite_policy"],
    "central_report_only": h["report_only_dimensions"],
    "honesty": (
        "standalone build_composite is P1 engineering canonical; "
        "Central AgentEvalResult.composite_score remains legacy_7dim "
        "with text/safety/refusal report-only (no silent reweight)"
    ),
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
}
path = evid / f"local-eval-p1-canonical-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "accuracy_claim": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "P1 canonical gate PASS (package scored; central legacy report-only; authorize=false)"
