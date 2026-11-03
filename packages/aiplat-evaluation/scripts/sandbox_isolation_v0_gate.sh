#!/usr/bin/env bash
# Sandbox isolation v0 — document + code honesty (≠ isolation certification).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DOC="$ROOT/docs/a3/SANDBOX_ISOLATION_V0.md"
EVID_DIR="${AIPLAT_EVAL_SANDBOX_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

[[ -f "$DOC" ]] || { echo "REFUSE: missing SANDBOX_ISOLATION_V0.md" >&2; exit 2; }

echo "== unit: docker sandbox =="
PYTHONPATH=. python3 -m pytest tests/test_b3l_sandbox_docker_cli.py -q --tb=line

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

src = Path("$ROOT/app/sandbox/docker_exec.py").read_text(encoding="utf-8")
assert "--network=none" in src, "docker_exec must pin network=none"
pol = Path("$ROOT/app/sandbox/policy.py").read_text(encoding="utf-8")
assert "sandbox_real_isolation" in pol or "network=none" in pol
doc = Path("$DOC").read_text(encoding="utf-8")
assert "sandbox_real_isolation=false" in doc
assert "≠ 隔离认证" in doc or "not" in doc.lower()

payload = {
    "schema": "eval.sandbox_isolation.gate.v0",
    "product_id": "evaluation",
    "environment": "local",
    "sandbox_real_isolation": False,
    "docker_network_none": True,
    "certified": False,
    "process_split_authorized": False,
    "accuracy_claim": False,
    "doc": "docs/a3/SANDBOX_ISOLATION_V0.md",
    "recorded_at": "$STAMP" or datetime.now(timezone.utc).isoformat(),
    "honesty": "network=none documented; not isolation certification; not authorize",
}
path = Path("$EVID_DIR") / f"local-eval-sandbox-isolation-v0-{payload['recorded_at']}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "sandbox_real_isolation": False}, ensure_ascii=False))
PY

echo "sandbox isolation v0 gate PASS (not certified; authorize=false)"
