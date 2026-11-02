#!/usr/bin/env bash
# Local EVAL A3 product-track closeout (B3/S1/P1 gates).
# NEVER sets process_split_authorized=true. Does NOT claim staging / B4.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_LOCAL_TRACK_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"

echo "== P1 scoring gate =="
bash "$ROOT/scripts/p1_local_gate.sh"

echo "== S1 security gate =="
bash "$ROOT/scripts/s1_local_gate.sh"

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
    "schema": "eval.local_track.closeout.v0",
    "product_id": "evaluation",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "sandbox_real_isolation": False,
    "security_live_attacks": False,
    "closed": ["B1-L", "B2-L", "B3-L", "S1", "P1", "P1.1", "P1.2"],
    "deferred": ["microVM_runtime", "live_tools", "B4-S", "B5-S", "B6"],
    "b4s_prep_doc": "docs/a3/B4S_PREP.md",
    "microvm_prep_doc": "docs/a3/MICROVM_PREP.md",
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
    "honesty": "local product track closeout — not staging authorize; not B4 PITR",
}
path = evid / f"local-eval-track-closeout-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"closeout": "ok", "evidence": str(path)}, ensure_ascii=False))
PY

echo "LOCAL TRACK CLOSEOUT PASS (authorize=false; next=host for B4-S / microVM runtime)"
