#!/usr/bin/env bash
# Pi D3 SOC local rehearsal — file sink only (NOT production alerting).
# Proves: enterprise=0 → no outbound; opt-in → local sink only.
# Marks checklist #5 as 🟨. Never sets d3_production_authorized=true.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DRILL_DIR="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${AIPLAT_PI_D3_SOC_REHEARSAL_DIR:-$(mktemp -d /tmp/aiplat-pi-d3-soc.XXXXXX)}"
mkdir -p "$WORK"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
echo "Pi D3 SOC rehearsal workdir=$WORK"

export AIPLAT_REHEARSAL_WORK="$WORK"
export AIPLAT_REHEARSAL_STAMP="$STAMP"
export AIPLAT_REHEARSAL_DRILL_DIR="$DRILL_DIR"
export AIPLAT_D3_CHECKLIST="$ROOT/packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md"

"$PY" - <<'PY'
import json
import os
from pathlib import Path

work = Path(os.environ["AIPLAT_REHEARSAL_WORK"])
stamp = os.environ["AIPLAT_REHEARSAL_STAMP"]
drill_dir = Path(os.environ["AIPLAT_REHEARSAL_DRILL_DIR"])
checklist = Path(os.environ["AIPLAT_D3_CHECKLIST"])

def emit(enterprise: str, sink: Path | None, event: dict) -> dict:
    """Minimal SOC hook: offline default drops; opt-in writes local sink only."""
    if enterprise != "1":
        return {"emitted": False, "reason": "AIPLAT_ENTERPRISE!=1", "outbound": False}
    if sink is None:
        return {"emitted": False, "reason": "no_sink", "outbound": False}
    # Never HTTP — file sink only in local rehearsal
    sink.parent.mkdir(parents=True, exist_ok=True)
    with sink.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"emitted": True, "sink": str(sink), "outbound": False}

def event(severity: str, msg: str) -> dict:
    """D2++ fixed local SOC schema (file-sink only)."""
    return {
        "kind": "pi.d3.alert",
        "severity": severity,
        "actor": "pi-d3-soc-rehearsal",
        "environment": "local",
        "msg": msg,
        "outbound_network": False,
    }

off = emit("0", work / "soc.jsonl", event("info", "should-drop"))
assert off["emitted"] is False and off["outbound"] is False
assert not (work / "soc.jsonl").exists()

on = emit("1", work / "soc.jsonl", event("warn", "local-sink-only"))
assert on["emitted"] is True and on["outbound"] is False
lines = (work / "soc.jsonl").read_text(encoding="utf-8").strip().splitlines()
assert len(lines) == 1
payload = json.loads(lines[0])
for req in ("kind", "severity", "actor", "environment"):
    assert req in payload, req
assert payload["environment"] == "local"
assert payload["kind"] == "pi.d3.alert"
assert payload["severity"] == "warn"
assert payload["actor"] == "pi-d3-soc-rehearsal"
assert "http://" not in lines[0] and "https://" not in lines[0]

out = drill_dir / f"soc-rehearsal-{stamp}.json"
out.write_text(
    json.dumps(
        {
            "kind": "pi_d3_soc_local_file_sink_not_production",
            "at": stamp,
            "environment": "local",
            "severity": "warn",
            "actor": "pi-d3-soc-rehearsal",
            "sink": str(work / "soc.jsonl"),
            "events_sample": [payload],
            "enterprise_off_drops": True,
            "enterprise_on_local_sink": True,
            "outbound_network": False,
            "production_soc": False,
            "production_signed": False,
            "note": "File sink mock only; checklist #5 partial until live SOC.",
            "workdir": str(work),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

text = checklist.read_text(encoding="utf-8")
text = text.replace(
    "| 5 | SOC/告警出口（enterprise opt-in）演练记录 | 运维 | ⬜ |",
    "| 5 | SOC/告警出口（enterprise opt-in）演练记录 | 运维 | 🟨 |",
)
assert "d3_production_authorized: false" in text
checklist.write_text(text, encoding="utf-8")
print("OK pi d3 SOC local rehearsal", out)
print("OK checklist #5 → 🟨 (d3_production still false)")
PY

echo "PASS: pi d3_soc_local_rehearsal stamp=$STAMP d3_production_authorized=false"
