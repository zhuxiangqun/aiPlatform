#!/usr/bin/env bash
# B1/B2 contract converge gate (standalone local).
# NEVER sets process_split_authorized=true. temporary_proxy must stay 0.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_CONTRACT_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "== unit: B1/B2 contract converge =="
PYTHONPATH=. python3 -m pytest \
  tests/test_b12_contract_converge.py \
  tests/test_b1l_execution_not_migrated.py \
  tests/test_b2l_allowlist_enqueue.py \
  -q --tb=line

export AIPLAT_EVAL_CONTRACT_GATE_STAMP="$STAMP"
export AIPLAT_EVAL_CONTRACT_GATE_EVID_DIR="$EVID_DIR"

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.contract.b12 import (
    count_temporary_proxy_markers,
    proxied_store_suffixes,
    residual_central_cohost_note,
)
from app.errors import execution_error

proxy_n = count_temporary_proxy_markers()
assert proxy_n == 0, proxy_n
sample = execution_error(
    code="sandbox_required",
    runner_id="skill_suite",
    detail="gate",
    retryable=False,
)
assert set(sample["error"]) >= {"code", "runner_id", "retryable", "detail"}

stamp = os.environ["AIPLAT_EVAL_CONTRACT_GATE_STAMP"]
evid = Path(os.environ["AIPLAT_EVAL_CONTRACT_GATE_EVID_DIR"])
payload = {
    "schema": "eval.b12.contract_gate.v0",
    "product_id": "evaluation",
    "phase": "B1-B2-contract",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "temporary_proxy_count": proxy_n,
    "proxied_store_suffixes": proxied_store_suffixes(),
    "residual": residual_central_cohost_note(),
    "honesty": (
        "standalone contract surface green; Central cohost residual is D1 default, "
        "not temporary_proxy; not staging authorize"
    ),
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
}
path = evid / f"local-eval-b12-contract-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "gate": "ok",
            "evidence": str(path),
            "temporary_proxy_count": proxy_n,
            "process_split_authorized": False,
        },
        ensure_ascii=False,
    )
)
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "B1/B2 contract gate PASS (temporary_proxy=0; authorize=false)"
