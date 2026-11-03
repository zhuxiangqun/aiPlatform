#!/usr/bin/env bash
# microVM Linux/KVM track gate — honesty + Darwin ineligible + optional Linux admit.
# NEVER sets process_split_authorized=true. NEVER claims sandbox_real_isolation.
# NEVER unlocks live skill tools.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_MICROVM_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "== unit: microVM prep + linux track =="
PYTHONPATH=. python3 -m pytest tests/test_microvm_prep.py tests/test_microvm_linux_track.py -q --tb=line

export AIPLAT_EVAL_MICROVM_GATE_STAMP="$STAMP"
export AIPLAT_EVAL_MICROVM_GATE_EVID_DIR="$EVID_DIR"

python3 - <<'PY'
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

from app.sandbox.microvm import (
    kvm_available,
    microvm_can_admit_runners,
    microvm_host_ok,
    microvm_status,
)
from app.sandbox.policy import sandbox_admits, sandbox_backend, sandbox_health
from app.sandbox.skill_policy import skill_suite_is_fixture

st = microvm_status()
health = sandbox_health()
assert st["process_split_authorized"] is False
assert st["sandbox_real_isolation"] is False
assert st["skill_suite_real_tools"] is False
assert st["guest_boot"] is False
assert st["eligible_on_darwin"] is False
assert health["sandbox_real_isolation"] is False
assert health["guest_boot"] is False
assert skill_suite_is_fixture({"mode": "live", "tools": ["shell"]}) is False

sysname = platform.system().lower()
if sysname == "darwin":
    assert kvm_available() is False
    assert microvm_host_ok() is False
    assert microvm_can_admit_runners() is False
    # Even with admit flag + enable + fake bin, Darwin cannot host_ok.
    os.environ["AIPLAT_EVAL_SANDBOX_BACKEND"] = "microvm"
    os.environ["AIPLAT_EVAL_MICROVM_ENABLED"] = "1"
    os.environ["AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS"] = "1"
    assert sandbox_admits("cli_probe") is False
    assert sandbox_admits(
        "skill_suite", payload={"mode": "live", "tools": ["shell"]}
    ) is False
elif sysname == "linux":
    # Honesty locks always; admit only when host_ok+flag (may be true on CI kvm).
    os.environ["AIPLAT_EVAL_SANDBOX_BACKEND"] = "microvm"
    assert sandbox_backend() == "microvm"
    assert sandbox_admits(
        "skill_suite", payload={"mode": "live", "tools": ["shell"]}
    ) is False
    if not microvm_can_admit_runners():
        assert sandbox_admits("cli_probe") is False

stamp = os.environ["AIPLAT_EVAL_MICROVM_GATE_STAMP"]
evid = Path(os.environ["AIPLAT_EVAL_MICROVM_GATE_EVID_DIR"])
payload = {
    "schema": "eval.microvm.linux_track_gate.v1",
    "product_id": "evaluation",
    "phase": "microVM-linux-track-v1",
    "environment": "local",
    "platform": sysname,
    "process_split_authorized": False,
    "accuracy_claim": False,
    "sandbox_real_isolation": False,
    "skill_suite_real_tools": False,
    "guest_boot": False,
    "kvm_available": kvm_available(),
    "microvm_host_ok": microvm_host_ok(),
    "microvm_admit_runners": microvm_can_admit_runners(),
    "microvm": st,
    "live_tools_admitted": False,
    "honesty": (
        "linux track v1 — host allowlist under microVM policy; "
        "guest_boot deferred; live tools denied; not certified isolation; "
        "not staging authorize; Darwin ineligible for with_microvm score"
    ),
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
}
path = evid / f"local-eval-microvm-linux-track-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "gate": "ok",
            "evidence": str(path),
            "platform": sysname,
            "kvm_available": st["kvm_available"],
            "microvm_host_ok": st["microvm_host_ok"],
            "microvm_admit_runners": st["microvm_admit_runners"],
            "block_reason": st["microvm_block_reason"],
            "guest_boot": False,
            "live_tools_admitted": False,
        },
        ensure_ascii=False,
    )
)
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "microVM linux track gate PASS (guest_boot=false; live_tools=false; authorize=false)"
