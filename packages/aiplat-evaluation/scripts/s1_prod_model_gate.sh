#!/usr/bin/env bash
# S1 live_llm against production-candidate model. NOT security certification.
# NEVER sets process_split_authorized=true. accuracy_claim stays false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROD_MODEL="${AIPLAT_EVAL_PROD_MODEL:-}"
SMOKE_MODEL="qwen2.5:3b"
ALLOW_SMOKE="${AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL:-0}"
AGG_OUT="${AIPLAT_EVAL_S1_PROD_AGGREGATE:-$ROOT/docs/a3/evidence/s1_prod_model_aggregate.v1.json}"
EVID_DIR="${AIPLAT_EVAL_S1_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"

if [[ -z "${PROD_MODEL}" ]]; then
  echo "REFUSE: set AIPLAT_EVAL_PROD_MODEL" >&2
  exit 2
fi
if [[ "${PROD_MODEL}" == "${SMOKE_MODEL}" && "${ALLOW_SMOKE}" != "1" ]]; then
  echo "REFUSE: refuse smoke-only model without AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL=1" >&2
  exit 2
fi
if [[ -z "${AIPLAT_EVAL_LLM_BASE_URL:-}" ]]; then
  echo "REFUSE: set AIPLAT_EVAL_LLM_BASE_URL" >&2
  exit 2
fi

export AIPLAT_EVAL_S1_LIVE=1
export AIPLAT_EVAL_LLM="${AIPLAT_EVAL_LLM:-1}"
# Force prod model — ignore leftover AIPLAT_EVAL_LLM_MODEL from smoke runs.
export AIPLAT_EVAL_LLM_MODEL="$PROD_MODEL"
export AIPLAT_EVAL_LLM_TIMEOUT="${AIPLAT_EVAL_LLM_TIMEOUT:-120}"
export AIPLAT_EVAL_S1_EVIDENCE_DIR="$EVID_DIR"

echo "== S1 prod-candidate model=${AIPLAT_EVAL_LLM_MODEL} =="
bash "$ROOT/scripts/s1_live_gate.sh"

DRILL_PATH="$(
python3 - <<'PY'
import json, os
from pathlib import Path

evid = Path(os.environ["AIPLAT_EVAL_S1_EVIDENCE_DIR"])
drills = sorted(evid.glob("local-eval-s1-live-gate-*.json"), key=lambda p: p.stat().st_mtime)
assert drills, "no s1 live drill found"
src = drills[-1]
data = json.loads(src.read_text(encoding="utf-8"))
data["prod_model"] = os.environ["AIPLAT_EVAL_LLM_MODEL"]
data["baseline_kind"] = "production_candidate"
data["honesty"] = (
    "S1 prod-candidate live_llm — ASR/leak/false_refusal; "
    "accuracy_claim=false; not security certification; no live skill tools"
)
src.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "gate": "ok" if data.get("ok") else "fail",
    "evidence": str(src),
    "prod_model": data.get("prod_model"),
    "asr": data.get("asr"),
    "leak_rate": data.get("leak_rate"),
    "llm_ok_n": data.get("llm_ok_n"),
    "accuracy_claim": False,
}, ensure_ascii=False), flush=True)
if not data.get("ok"):
    raise SystemExit(1)
print(str(src), flush=True)
PY
)"
DRILL_PATH="$(printf '%s\n' "$DRILL_PATH" | tail -n 1)"

python3 "$ROOT/scripts/s1_prod_summarize.py" \
  --drill "$DRILL_PATH" \
  --out "$AGG_OUT" \
  --prod-model "$PROD_MODEL"

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "S1 prod-model gate done (authorize=false; not security cert; accuracy_claim=false; aggregate=$AGG_OUT)"
