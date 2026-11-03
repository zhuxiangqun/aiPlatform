#!/usr/bin/env bash
# microVM guest_boot authorize gate.
# NEVER sets process_split_authorized=true. NEVER claims sandbox_real_isolation.
# NEVER unlocks live skill tools. Darwin always guest_boot=false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_MICROVM_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "== unit: microVM guest_boot =="
PYTHONPATH=. python3 -m pytest tests/test_microvm_guest_boot.py -q --tb=line

export AIPLAT_EVAL_MICROVM_GATE_STAMP="$STAMP"
export AIPLAT_EVAL_MICROVM_GATE_EVID_DIR="$EVID_DIR"

python3 - <<'PY'
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

from app.sandbox.guest_boot import probe_guest_boot
from app.sandbox.microvm import (
    clear_guest_boot_cache,
    kvm_available,
    microvm_guest_boot_authorized,
    microvm_host_ok,
    microvm_status,
)
from app.sandbox.policy import sandbox_health

clear_guest_boot_cache()
st = microvm_status()
health = sandbox_health()
assert st["process_split_authorized"] is False
assert st["sandbox_real_isolation"] is False
assert st["skill_suite_real_tools"] is False
assert health["sandbox_real_isolation"] is False
assert st["eligible_on_darwin"] is False

sysname = platform.system().lower()
probe = None
if sysname == "darwin":
    assert kvm_available() is False
    assert microvm_host_ok() is False
    assert microvm_guest_boot_authorized() is False
    assert st["guest_boot"] is False
    probe = probe_guest_boot()
    assert probe["ok"] is False
    assert probe["audit"]["guest_boot"] is False
elif sysname == "linux":
    # Without operator assets/flag, authorize stays false — honesty lock.
    if not microvm_guest_boot_authorized():
        probe = probe_guest_boot()
        assert probe["ok"] is False
        assert st["guest_boot"] is False
    else:
        probe = probe_guest_boot()
        # Real KVM+assets may succeed or fail; never flip process_split.
        assert microvm_status()["process_split_authorized"] is False

st2 = microvm_status()
stamp = os.environ["AIPLAT_EVAL_MICROVM_GATE_STAMP"]
evid = Path(os.environ["AIPLAT_EVAL_MICROVM_GATE_EVID_DIR"])
payload = {
    "schema": "eval.microvm.guest_boot_gate.v1",
    "product_id": "evaluation",
    "phase": "microVM-guest-boot-authorize-v2",
    "environment": "local",
    "platform": sysname,
    "process_split_authorized": False,
    "accuracy_claim": False,
    "sandbox_real_isolation": False,
    "skill_suite_real_tools": False,
    "guest_boot": bool(st2.get("guest_boot")),
    "guest_boot_authorized": bool(st2.get("guest_boot_authorized")),
    "guest_boot_flag": bool(st2.get("guest_boot_flag")),
    "kvm_available": kvm_available(),
    "microvm_host_ok": microvm_host_ok(),
    "microvm": st2,
    "probe": {
        "ok": bool(probe.get("ok")) if probe else None,
        "stderr": (probe or {}).get("stderr"),
        "guest_boot": bool((probe or {}).get("audit", {}).get("guest_boot")),
    },
    "honesty": (
        "guest_boot authorize = GUEST_BOOT+assets+InstanceStart; "
        "≠ process_split_authorized; ≠ live tools; ≠ isolation cert; "
        "Darwin ineligible"
    ),
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
}
path = evid / f"local-eval-microvm-guest-boot-gate-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "gate": "ok",
            "evidence": str(path),
            "platform": sysname,
            "guest_boot": st2["guest_boot"],
            "guest_boot_authorized": st2["guest_boot_authorized"],
            "process_split_authorized": False,
            "block_reason": st2["microvm_block_reason"],
        },
        ensure_ascii=False,
    )
)
PY

echo "== process_split authorize status (must stay locked) =="
STATUS_JSON="$(bash "$ROOT/scripts/a3_split_authorize.sh" status)"
python3 -c "
import json, sys
d=json.loads(sys.argv[1])
assert d.get('process_split_authorized_doc') is False
assert d.get('process_split_authorized_status_json') is False
# Refuse flip without all-green + signed live
assert d.get('ready_to_authorize') is False
print('process_split authorize still locked (expected)')
" "$STATUS_JSON"

echo "microVM guest_boot gate PASS (process_split_authorized=false)"
