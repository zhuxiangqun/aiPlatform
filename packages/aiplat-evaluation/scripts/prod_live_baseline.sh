#!/usr/bin/env bash
# Production-candidate model live baseline (25×3). accuracy_claim=false.
# NEVER sets process_split_authorized=true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROD_MODEL="${AIPLAT_EVAL_PROD_MODEL:-}"
SMOKE_MODEL="qwen2.5:3b"
ALLOW_SMOKE="${AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL:-0}"

if [[ -z "${PROD_MODEL}" ]]; then
  echo "REFUSE: set AIPLAT_EVAL_PROD_MODEL to your production-candidate model" >&2
  exit 2
fi
if [[ "${PROD_MODEL}" == "${SMOKE_MODEL}" && "${ALLOW_SMOKE}" != "1" ]]; then
  echo "REFUSE: AIPLAT_EVAL_PROD_MODEL=${PROD_MODEL} is the 3B smoke default; set a prod candidate or AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL=1" >&2
  exit 2
fi

export AIPLAT_EVAL_LLM_LIVE="${AIPLAT_EVAL_LLM_LIVE:-1}"
export AIPLAT_EVAL_LLM="${AIPLAT_EVAL_LLM:-1}"
export AIPLAT_EVAL_LLM_MODEL="${AIPLAT_EVAL_LLM_MODEL:-$PROD_MODEL}"
export AIPLAT_EVAL_LIVE_LLM_TASKS="${AIPLAT_EVAL_LIVE_LLM_TASKS:-$ROOT/docs/a3/prod_live_tasks.v0.json}"
export AIPLAT_EVAL_LIVE_LLM_REPEATS="${AIPLAT_EVAL_LIVE_LLM_REPEATS:-3}"
export AIPLAT_EVAL_LIVE_LLM_EVIDENCE_DIR="${AIPLAT_EVAL_LIVE_LLM_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
export AIPLAT_EVAL_LLM_TIMEOUT="${AIPLAT_EVAL_LLM_TIMEOUT:-120}"

if [[ -z "${AIPLAT_EVAL_LLM_BASE_URL:-}" ]]; then
  echo "REFUSE: set AIPLAT_EVAL_LLM_BASE_URL (OpenAI-compatible provider)" >&2
  exit 2
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
export AIPLAT_EVAL_PROD_LIVE_STAMP="$STAMP"

echo "== prod live baseline model=${AIPLAT_EVAL_LLM_MODEL} repeats=${AIPLAT_EVAL_LIVE_LLM_REPEATS} =="
bash "$ROOT/scripts/live_llm_smoke.sh"

# Rename/annotate latest smoke evidence as prod-live for clarity
python3 - <<'PY'
import json, os
from pathlib import Path

evid = Path(os.environ["AIPLAT_EVAL_LIVE_LLM_EVIDENCE_DIR"])
stamp = os.environ["AIPLAT_EVAL_PROD_LIVE_STAMP"]
cands = sorted(evid.glob("local-eval-live-llm-*.json"))
assert cands, "missing live_llm smoke evidence"
src = cands[-1]
data = json.loads(src.read_text(encoding="utf-8"))
data["schema"] = "eval.prod_live.baseline.v0"
data["baseline_kind"] = "production_candidate"
data["prod_model"] = os.environ.get("AIPLAT_EVAL_PROD_MODEL")
data["accuracy_claim"] = False
data["honesty"] = (
    "production-candidate live baseline — latency/cost/fail rates; "
    "not G2b accuracy; not staging authorize; not security certification"
)
dst = evid / f"local-eval-prod-live-{stamp}.json"
dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "gate": "ok" if data.get("gate_ok") else "fail",
    "evidence": str(dst),
    "source_smoke": str(src),
    "prod_model": data.get("prod_model"),
    "task_count": data.get("task_count"),
    "accuracy_claim": False,
}, ensure_ascii=False))
raise SystemExit(0 if data.get("gate_ok") else 1)
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "prod live baseline done (authorize=false; accuracy_claim=false)"
