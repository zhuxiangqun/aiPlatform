#!/usr/bin/env bash
# Local EVAL A3 product-track closeout (P1/S1/live_llm/session gates).
# NEVER sets process_split_authorized=true. Does NOT claim staging / B4.
# Stub-safe by default; optional live LLM via env on child gates.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_LOCAL_TRACK_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"

# Hermetic stub path unless caller opts into live provider.
# Prevents a leftover AIPLAT_EVAL_LLM_BASE_URL in the shell from silently
# turning closeout into a multi-minute Ollama run.
CLOSEOUT_LIVE="${AIPLAT_EVAL_CLOSEOUT_LIVE:-0}"
if [[ "${CLOSEOUT_LIVE}" != "1" && "${AIPLAT_EVAL_LLM_LIVE:-0}" != "1" ]]; then
  # Clear leftover live flags from the parent shell (fixture healthz must stay false).
  unset AIPLAT_EVAL_LLM_BASE_URL AIPLAT_EVAL_LLM_MODEL AIPLAT_EVAL_S1_LIVE \
    AIPLAT_EVAL_LLM_LIVE || true
  export AIPLAT_EVAL_LLM=stub
  export AIPLAT_EVAL_LLM_STUB_OUTPUT="${AIPLAT_EVAL_LLM_STUB_OUTPUT:-I cannot help with that request.}"
fi

echo "== P1 scoring + dimensions gate =="
bash "$ROOT/scripts/p1_local_gate.sh"

echo "== S1 security fixture gate =="
bash "$ROOT/scripts/s1_local_gate.sh"

echo "== S1 live_llm gate (stub unless AIPLAT_EVAL_CLOSEOUT_LIVE=1) =="
bash "$ROOT/scripts/s1_live_gate.sh"

echo "== live LLM smoke (stub unless AIPLAT_EVAL_LLM_LIVE=1) =="
bash "$ROOT/scripts/live_llm_smoke.sh"

echo "== session_eval v0 gate =="
bash "$ROOT/scripts/session_v0_gate.sh"

echo "== session_eval v1 gate =="
bash "$ROOT/scripts/session_v1_gate.sh"

echo "== preference v0 gate (fixture solo ≠ human κ) =="
bash "$ROOT/scripts/preference_v0_gate.sh"

echo "== P2-1 context_mgmt v0 gate =="
bash "$ROOT/scripts/context_v0_gate.sh"

echo "== P2-2 memory_persist v0 gate =="
bash "$ROOT/scripts/memory_v0_gate.sh"

echo "== P2-3 self_learn v0 gate =="
bash "$ROOT/scripts/self_learn_v0_gate.sh"

echo "== authorize status (must stay false) =="
STATUS_JSON="$(bash "$ROOT/scripts/a3_split_authorize.sh" status)"
echo "$STATUS_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('ready_to_authorize') is False
assert d.get('process_split_authorized_doc') is False
assert d.get('process_split_authorized_status_json') is False
print('authorize still locked')
"

python3 - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone

stamp = "${STAMP}"
evid = Path("${EVID_DIR}")
payload = {
    "schema": "eval.local_track.closeout.v3",
    "product_id": "evaluation",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "sandbox_real_isolation": False,
    # Pack executed under live_llm (LLM may be stub); ≠ security certification.
    "security_live_attacks": True,
    "not_security_certification": True,
    "local_first": True,
    "not_public_release": True,
    "closed": [
        "B1-L",
        "B2-L",
        "B3-L",
        "S1",
        "S1_live",
        "P1",
        "P1.1",
        "P1.2",
        "P1_dimensions",
        "live_llm_smoke",
        "session_v0",
        "session_v1",
        "preference_v0_fixture",
        "context_mgmt_v0",
        "memory_persist_v0",
        "self_learn_v0",
    ],
    "deferred": [
        "microVM_runtime",
        "live_tools",
        "B4-S_host",
        "B5-S",
        "B6",
        "public_A1_release",
        "P2-4_prod_governance",
        "process_split_authorize",
    ],
    "b4s_prep_doc": "docs/a3/B4S_PREP.md",
    "microvm_prep_doc": "docs/a3/MICROVM_PREP.md",
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
    "honesty": (
        "local product track closeout v3 — +P2 context/memory/self_learn; "
        "local-first; not public release; not staging authorize; not accuracy; not security cert"
    ),
}
path = evid / f"local-eval-track-closeout-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"closeout": "ok", "schema": payload["schema"], "evidence": str(path)}, ensure_ascii=False))
PY

echo "LOCAL TRACK CLOSEOUT PASS (v3; authorize=false; local-first; public release deferred)"
