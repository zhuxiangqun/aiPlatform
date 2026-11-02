#!/usr/bin/env bash
# microVM prep gate — prove probe + live tools still denied.
# NEVER sets process_split_authorized=true. NEVER claims sandbox_real_isolation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_MICROVM_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "== unit: microVM prep =="
PYTHONPATH=. python3 -m pytest tests/test_microvm_prep.py -q --tb=line

export AIPLAT_EVAL_MICROVM_GATE_STAMP="$STAMP"
export AIPLAT_EVAL_MICROVM_GATE_EVID_DIR="$EVID_DIR"

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.sandbox.microvm import microvm_status
from app.sandbox.policy import sandbox_admits, sandbox_backend, sandbox_health
from app.sandbox.skill_policy import skill_suite_is_fixture

st = microvm_status()
health = sandbox_health()
assert st["process_split_authorized"] is False
assert st["sandbox_real_isolation"] is False
assert st["skill_suite_real_tools"] is False
assert health["sandbox_real_isolation"] is False
assert health["skill_suite_real_tools"] is False
assert skill_suite_is_fixture({"mode": "live", "tools": ["shell"]}) is False
# Even if operator points backend at microvm, prep admits nothing.
os.environ["AIPLAT_EVAL_SANDBOX_BACKEND"] = "microvm"
assert sandbox_backend() == "microvm"
assert sandbox_admits("skill_suite", payload={"mode": "live", "tools": ["shell"]}) is False
assert sandbox_admits("cli_probe") is False

stamp = os.environ["AIPLAT_EVAL_MICROVM_GATE_STAMP"]
evid = Path(os.environ["AIPLAT_EVAL_MICROVM_GATE_EVID_DIR"])
payload = {
    "schema": "eval.microvm.prep_gate.v0",
    "product_id": "evaluation",
    "phase": "microVM-prep",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "sandbox_real_isolation": False,
    "skill_suite_real_tools": False,
    "microvm": st,
    "sandbox_backend_forced": "microvm",
    "live_tools_admitted": False,
    "honesty": (
        "prep probe only — live skill tools denied; "
        "not certified isolation; not staging authorize"
    ),
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
}
path = evid / f"local-eval-microvm-prep-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "gate": "ok",
            "evidence": str(path),
            "microvm_ready": st["microvm_ready"],
            "block_reason": st["microvm_block_reason"],
            "live_tools_admitted": False,
        },
        ensure_ascii=False,
    )
)
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "microVM prep gate PASS (live_tools=false; authorize=false; isolation=false)"
