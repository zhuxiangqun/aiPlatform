#!/usr/bin/env bash
# G2b accuracy closeout gate — model pass-rate vs adjudicated gold.
# NEVER sets accuracy_claim=true without attestation.
# NEVER sets process_split_authorized=true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

EVID="$ROOT/docs/a3/evidence"
A="$EVID/g2b_annotator_a.labels.v1.json"
B="$EVID/g2b_annotator_b.labels.v1.json"
ADJ="$EVID/g2b_adjudication.v1.json"
GOLD="$EVID/g2b_adjudicated_gold.v1.json"
AGG="$EVID/g2b_accuracy_aggregate.v1.json"

echo "== unit: g2b accuracy closeout =="
PYTHONPATH=. python3 -m pytest tests/test_g2b_accuracy_closeout.py -q --tb=line

echo "== verify committed gold/aggregate (claim stays false) =="
# Recompute to stdout only — do not rewrite committed evidence (SHA locked in manifest).
# SSOT: tracked n=100 evidence labels (human_pack/ is gitignored).
python3 "$ROOT/scripts/g2b_accuracy_closeout.py" \
  --a "$A" \
  --b "$B" \
  --adjudication "$ADJ" >/tmp/g2b_accuracy_closeout_gate.out
python3 - <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path("docs/a3/evidence")
agg = json.loads((root / "g2b_accuracy_aggregate.v1.json").read_text(encoding="utf-8"))
gold = json.loads((root / "g2b_adjudicated_gold.v1.json").read_text(encoding="utf-8"))
adj = json.loads((root / "g2b_adjudication.v1.json").read_text(encoding="utf-8"))
assert agg["accuracy_claim"] is False
assert agg["not_accuracy_certification"] is True
assert agg["n"] == 100
assert agg["pass_n"] == 80
assert agg["pass_rate"] == 0.8
assert agg["disputed_n"] == 8
assert len(adj["disputes"]) == 8
assert gold["n"] == 100
assert all(isinstance(r.get("gold_pass"), bool) for r in gold["labels"])
assert agg["wilson_ci95"][0] >= 0.70
gate_out = json.loads(Path("/tmp/g2b_accuracy_closeout_gate.out").read_text(encoding="utf-8").strip().splitlines()[-1])
assert gate_out["n"] == 100
assert abs(gate_out["pass_rate"] - 0.8) < 1e-9
assert gate_out["accuracy_claim"] is False
r = subprocess.run(
    [
        sys.executable,
        "scripts/g2b_accuracy_closeout.py",
        "--a", str(root / "g2b_annotator_a.labels.v1.json"),
        "--b", str(root / "g2b_annotator_b.labels.v1.json"),
        "--adjudication", str(root / "g2b_adjudication.v1.json"),
        "--claim-ready",
    ],
    capture_output=True,
    text=True,
    check=True,
)
out = json.loads(r.stdout.strip().splitlines()[-1])
assert out["accuracy_claim"] is False
assert out["claim_refuse_reason"] == "attestation_missing"
assert out["n"] == 100
assert abs(out["pass_rate"] - 0.8) < 1e-9
print(json.dumps({
    "gate": "ok",
    "pass_rate": agg["pass_rate"],
    "wilson_ci95": agg["wilson_ci95"],
    "disputed_n": agg["disputed_n"],
    "accuracy_claim": False,
    "section4": {"pass_rate_met": True, "wilson_lo_met": True},
    "pending_human_confirm": adj.get("pending_human_confirm"),
}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "g2b accuracy closeout gate PASS (accuracy_claim=false; process_split=false)"
