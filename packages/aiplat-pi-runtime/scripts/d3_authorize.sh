#!/usr/bin/env bash
# Pi D3 production-claim authorize gate.
# status|authorize — authorize ONLY if D3_CHECKLIST all ✅ + signed live; else REFUSE.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHECKLIST="$ROOT/packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md"
STATUS_JSON="$ROOT/packages/aiplat-pi-runtime/docs/d3/PREP_STATUS.json"
CHART="$ROOT/packages/aiplat-pi-runtime/chart/Chart.yaml"
DRILL_DIR="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
CMD="${1:-status}"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_REPO_ROOT="${AIPLAT_REPO_ROOT:-$ROOT}"
export AIPLAT_D3_CHECKLIST="${AIPLAT_D3_CHECKLIST:-$CHECKLIST}"
export AIPLAT_D3_STATUS_JSON="${AIPLAT_D3_STATUS_JSON:-$STATUS_JSON}"
export AIPLAT_D3_CHART="${AIPLAT_D3_CHART:-$CHART}"
export AIPLAT_LIVE_DRILL_DIR="${AIPLAT_LIVE_DRILL_DIR:-$DRILL_DIR}"
export AIPLAT_D3_CMD="$CMD"

"$PY" - <<'PY'
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
sys.path.insert(0, str(root / "scripts" / "lib"))
from aiplat_live_evidence import require_signed_live  # noqa: E402

checklist = Path(os.environ["AIPLAT_D3_CHECKLIST"])
status_path = Path(os.environ["AIPLAT_D3_STATUS_JSON"])
chart = Path(os.environ["AIPLAT_D3_CHART"])
drill_dir = Path(os.environ["AIPLAT_LIVE_DRILL_DIR"])
cmd = os.environ["AIPLAT_D3_CMD"]

text = checklist.read_text(encoding="utf-8")
rows = []
for line in text.splitlines():
    m = re.match(r"^\|\s*(\d+)\s*\|.*\|\s*([✅🟨⬜])\s*\|", line)
    if m:
        rows.append((int(m.group(1)), m.group(2)))
if not rows:
    print("FAIL: no checklist rows", file=sys.stderr)
    sys.exit(2)

all_green = all(mark == "✅" for _, mark in rows)
marks = {n: m for n, m in rows}
authorized_doc = "d3_production_authorized: true" in text and "d3_production_authorized: false" not in text
status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
status_flag = bool(status.get("d3_production_authorized"))
chart_ok = chart.is_file() and 'aiplat.d3_production_authorized: "false"' in chart.read_text(encoding="utf-8")
live_ok, live_summary = require_signed_live(drill_dir)

report = {
    "gate": "pi_d3_authorize",
    "checklist_marks": marks,
    "all_green": all_green,
    "live_evidence": live_summary,
    "live_production_signed": live_ok,
    "d3_production_authorized_doc": authorized_doc,
    "d3_production_authorized_status_json": status_flag,
    "chart_d3_false_annotation": chart_ok,
    "ready_to_authorize": bool(all_green and live_ok and not authorized_doc),
}
print(json.dumps(report, ensure_ascii=False, indent=2))

if cmd == "status":
    sys.exit(0)
if cmd != "authorize":
    print("usage: d3_authorize.sh status|authorize", file=sys.stderr)
    sys.exit(2)

if not all_green:
    print(
        f"REFUSED: pi d3_authorize — checklist not all ✅ (marks={marks}); 🟨≠authorize",
        file=sys.stderr,
    )
    sys.exit(1)
if not live_ok:
    print(
        "REFUSED: pi d3_authorize — need live-*.json with production_signed=true "
        f"(got={live_summary})",
        file=sys.stderr,
    )
    sys.exit(1)

text2 = text.replace("d3_production_authorized: false", "d3_production_authorized: true")
checklist.write_text(text2, encoding="utf-8")
status["d3_production_authorized"] = True
status["live_evidence"] = live_summary
status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
if chart.is_file():
    c = chart.read_text(encoding="utf-8").replace(
        'aiplat.d3_production_authorized: "false"',
        'aiplat.d3_production_authorized: "true"',
    )
    chart.write_text(c, encoding="utf-8")
print("AUTHORIZED: d3_production_authorized=true")
PY
