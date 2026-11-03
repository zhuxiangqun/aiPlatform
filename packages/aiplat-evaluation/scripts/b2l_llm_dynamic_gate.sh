#!/usr/bin/env bash
# B2-L LLM dynamic execute gate (stub always; optional live provider).
# NEVER sets process_split_authorized=true. accuracy_claim stays false.
#
# Default: stub Worker e2e (CI-safe).
# Optional live: AIPLAT_EVAL_LLM_LIVE=1 + AIPLAT_EVAL_LLM_BASE_URL=independent provider
#   (must NOT look like Central :8000 /api/core).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_LLM_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
LIVE_JSON_FILE="${EVID_DIR}/.live-probe-${STAMP}.json"

echo "== unit: prompt_eval llm + dynamic worker =="
PYTHONPATH=. python3 -m pytest \
  tests/test_prompt_eval_llm.py \
  tests/test_b2l_llm_dynamic_execute.py -q --tb=line

LIVE="${AIPLAT_EVAL_LLM_LIVE:-0}"
LIVE_OK=false

if [[ "$LIVE" == "1" || "$LIVE" == "true" || "$LIVE" == "yes" ]]; then
  echo "== optional live provider probe =="
  set +e
  PYTHONPATH=. python3 - <<PY >"$LIVE_JSON_FILE"
import json, os, sys
from app.llm.client import (
    assert_provider_independence,
    complete_text,
    looks_like_central_llm_url,
    provider_base_url,
)
base = provider_base_url()
out = {
    "attempted": True,
    "base_url_set": bool(base),
    "looks_like_central": looks_like_central_llm_url(base),
    "ok": False,
    "detail": "",
    "accuracy_claim": False,
    "central_http": False,
}
if not base:
    out["detail"] = "missing_AIPLAT_EVAL_LLM_BASE_URL"
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(2)
try:
    assert_provider_independence(base)
except ValueError as exc:
    out["detail"] = str(exc)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(3)
os.environ["AIPLAT_EVAL_LLM"] = "http"
r = complete_text("ping", job_id="live-gate", tenant_id="local", purpose="prompt_eval")
out["ok"] = bool(r.get("ok"))
audit = r.get("audit") if isinstance(r.get("audit"), dict) else {}
out["detail"] = str(audit.get("detail") or ("ok" if out["ok"] else "provider_failed"))
out["model"] = audit.get("model")
out["latency_ms"] = audit.get("latency_ms")
out["central_http"] = bool(audit.get("central_http"))
print(json.dumps(out, ensure_ascii=False))
sys.exit(0 if out["ok"] else 4)
PY
  LIVE_RC=$?
  set -e
  if [[ "$LIVE_RC" -eq 0 ]]; then
    LIVE_OK=true
  else
    echo "LIVE provider probe failed rc=$LIVE_RC (stub path already passed; honesty recorded)"
    cat "$LIVE_JSON_FILE" || true
  fi
else
  echo '{"attempted":false,"ok":false,"detail":"live_not_requested"}' >"$LIVE_JSON_FILE"
fi

export AIPLAT_EVAL_LLM_GATE_STAMP="$STAMP"
export AIPLAT_EVAL_LLM_GATE_EVID_DIR="$EVID_DIR"
export AIPLAT_EVAL_LLM_GATE_LIVE_FILE="$LIVE_JSON_FILE"
export AIPLAT_EVAL_LLM_GATE_LIVE_OK="$LIVE_OK"
export AIPLAT_EVAL_LLM_GATE_LIVE_REQ="$LIVE"

python3 - <<'PY'
import json, os
from pathlib import Path
from datetime import datetime, timezone

stamp = os.environ["AIPLAT_EVAL_LLM_GATE_STAMP"]
evid = Path(os.environ["AIPLAT_EVAL_LLM_GATE_EVID_DIR"])
live_file = Path(os.environ["AIPLAT_EVAL_LLM_GATE_LIVE_FILE"])
live_detail = json.loads(live_file.read_text(encoding="utf-8"))
live_req = os.environ.get("AIPLAT_EVAL_LLM_GATE_LIVE_REQ", "0") in ("1", "true", "yes")
live_ok = os.environ.get("AIPLAT_EVAL_LLM_GATE_LIVE_OK") == "true"
payload = {
    "schema": "eval.b2l.llm_dynamic_gate.v0",
    "product_id": "evaluation",
    "phase": "B2-L",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "stub_path": "pass",
    "live_requested": live_req,
    "live_ok": live_ok,
    "live_detail": live_detail,
    "honesty": (
        "stub Worker e2e proves dynamic prompt_eval without Central; "
        "live_ok only when independent provider answered; not G2b accuracy; not staging authorize"
    ),
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
}
path = evid / f"local-eval-b2l-llm-dynamic-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
try:
    live_file.unlink()
except OSError:
    pass
print(json.dumps({"gate": "ok", "evidence": str(path), "live_ok": live_ok, "accuracy_claim": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "B2-L LLM dynamic gate PASS (stub; live_ok=${LIVE_OK}; authorize=false)"
