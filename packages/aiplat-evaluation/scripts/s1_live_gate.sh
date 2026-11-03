#!/usr/bin/env bash
# S1 live_llm attack pack gate (optional real LLM; stub CI-safe path).
# Docker wrap --network=none. NO live skill tools. NOT a security certification.
# NEVER sets process_split_authorized=true. accuracy_claim stays false.
#
# Stub (CI):
#   bash packages/aiplat-evaluation/scripts/s1_live_gate.sh
#
# Live Ollama:
#   AIPLAT_EVAL_S1_LIVE=1 AIPLAT_EVAL_LLM=1 \
#   AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
#   AIPLAT_EVAL_LLM_MODEL=qwen2.5:3b \
#   bash packages/aiplat-evaluation/scripts/s1_live_gate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_S1_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
WORK="${AIPLAT_EVAL_S1_LIVE_WORK:-$(mktemp -d /tmp/aiplat-eval-s1-live.XXXXXX)}"
PACK="${AIPLAT_EVAL_S1_ATTACK_PACK:-$ROOT/docs/a3/s1_live_attacks.v0.json}"
mkdir -p "$EVID_DIR" "$WORK"

FAKE_DOCKER="${WORK}/fake-docker"
cat >"$FAKE_DOCKER" <<'SH'
#!/bin/sh
# Honor docker run --network=none presence for audit honesty in tests.
exit 0
SH
chmod +x "$FAKE_DOCKER"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export AIPLAT_EVAL_SANDBOX_BACKEND=docker
export AIPLAT_EVAL_DOCKER_BIN="${AIPLAT_EVAL_DOCKER_BIN:-$FAKE_DOCKER}"
export AIPLAT_EVAL_S1_EVIDENCE_DIR="$EVID_DIR"
export AIPLAT_EVAL_S1_STAMP="$STAMP"
export AIPLAT_EVAL_S1_ATTACK_PACK="$PACK"

echo "== unit: S1 fixture + live_llm (S1_LIVE unset for fixture honesty) =="
env -u AIPLAT_EVAL_S1_LIVE PYTHONPATH=. python3 -m pytest \
  tests/test_s1_security_fixture.py \
  tests/test_s1_live_attacks.py -q --tb=line

# Unlock live_llm only for the pack execute step.
export AIPLAT_EVAL_S1_LIVE=1
# Default stub LLM so gate is CI-safe unless caller set real provider.
if [[ -z "${AIPLAT_EVAL_LLM_BASE_URL:-}" ]]; then
  export AIPLAT_EVAL_LLM=stub
  export AIPLAT_EVAL_LLM_STUB_OUTPUT="${AIPLAT_EVAL_LLM_STUB_OUTPUT:-I cannot help with that request.}"
else
  export AIPLAT_EVAL_LLM="${AIPLAT_EVAL_LLM:-1}"
fi

echo "== live_llm pack execute =="
PYTHONPATH=. python3 - <<'PY'
import json, os
from pathlib import Path
from app.worker.runners import execute_runner

pack_path = Path(os.environ["AIPLAT_EVAL_S1_ATTACK_PACK"])
pack = json.loads(pack_path.read_text(encoding="utf-8"))
cases = [c for c in pack.get("cases") or [] if isinstance(c, dict)]
assert len(cases) >= 20, f"need >=20 cases, got {len(cases)}"

out = execute_runner(
    {
        "job_id": "s1-live-gate",
        "tenant_id": "local-s1",
        "runner_id": "security_redteam",
        "payload": {
            "mode": "live_llm",
            "suite_id": "s1_live_attacks.v0",
            "cases": cases,
        },
    }
)
assert out.get("accuracy_claim") is False
assert out["evidence"].get("live_skill_tools") is False
assert out["evidence"].get("not_security_certification") is True
assert out["evidence"].get("docker_network") == "none"
m = out.get("metrics") or {}
assert "asr" in m and "leak_rate" in m and "false_refusal_rate" in m
assert float(m.get("cases") or 0) >= 20
# Provider must actually answer at least once — empty/fail-all must not PASS.
assert out.get("ok") is True, out.get("detail") or "live pack not ok"
assert int(out["evidence"].get("llm_ok_n") or 0) > 0
assert float(m.get("llm_ok_n") or 0) > 0

stamp = os.environ.get("AIPLAT_EVAL_S1_STAMP") or ""
evid = Path(os.environ["AIPLAT_EVAL_S1_EVIDENCE_DIR"])
payload = {
    "schema": "eval.s1.live_gate.v0",
    "product_id": "evaluation",
    "phase": "S1",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "security_live_attacks": True,
    "not_security_certification": True,
    "live_skill_tools": False,
    "docker_network": "none",
    "suite_id": "s1_live_attacks.v0",
    "cases": float(m.get("cases") or 0),
    "asr": m.get("asr"),
    "leak_rate": m.get("leak_rate"),
    "false_refusal_rate": m.get("false_refusal_rate"),
    "llm_audits_n": (out.get("evidence") or {}).get("llm_audits_n"),
    "llm_ok_n": (out.get("evidence") or {}).get("llm_ok_n"),
    "llm_fail_n": (out.get("evidence") or {}).get("llm_fail_n"),
    "mode": out.get("mode"),
    "ok": out.get("ok"),
    "recorded_at": stamp,
    "honesty": (
        "S1 live_llm attack pack — ASR/leak/false_refusal are security metrics; "
        "not accuracy; not security certification; no live skill tools"
    ),
}
path = evid / f"local-eval-s1-live-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "gate": "ok",
    "evidence": str(path),
    "asr": m.get("asr"),
    "leak_rate": m.get("leak_rate"),
    "false_refusal_rate": m.get("false_refusal_rate"),
    "accuracy_claim": False,
}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "S1 live_llm gate PASS (authorize=false; not security cert)"
