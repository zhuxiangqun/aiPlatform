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
python3 "$ROOT/scripts/g2b_accuracy_closeout.py" \
  --a "$A" \
  --b "$B" \
  --adjudication "$ADJ" >/tmp/g2b_accuracy_closeout_gate.out
python3 - <<'PY'
import json
from pathlib import Path
root = Path("docs/a3/evidence")
agg = json.loads((root / "g2b_accuracy_aggregate.v1.json").read_text(encoding="utf-8"))
gold = json.loads((root / "g2b_adjudicated_gold.v1.json").read_text(encoding="utf-8"))
adj = json.loads((root / "g2b_adjudication.v1.json").read_text(encoding="utf-8"))
assert agg["accuracy_claim"] is False
assert agg["not_accuracy_certification"] is True
assert agg["n"] == 30
assert agg["disputed_n"] == 5
assert len(adj["disputes"]) == 5
assert gold["n"] == 30
assert all(isinstance(r.get("gold_pass"), bool) for r in gold["labels"])
# claim-ready without attestation must still refuse
import subprocess, sys
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
print(json.dumps({
    "gate": "ok",
    "pass_rate": agg["pass_rate"],
    "wilson_ci95": agg["wilson_ci95"],
    "disputed_n": agg["disputed_n"],
    "accuracy_claim": False,
    "pending_human_confirm": adj.get("pending_human_confirm"),
}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "g2b accuracy closeout gate PASS (accuracy_claim=false; process_split=false)"
