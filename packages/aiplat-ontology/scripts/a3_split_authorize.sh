#!/usr/bin/env bash
# Ontology A3 process-split authorize gate.
# status|authorize — authorize ONLY if SPLIT_CHECKLIST all ✅ + signed live; else REFUSE.
# Never Accepts ADR. ADR may already be Accepted（有条件）.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
CHECKLIST="$ROOT/packages/aiplat-ontology/docs/a3/SPLIT_CHECKLIST.md"
STATUS_JSON="$ROOT/packages/aiplat-ontology/docs/a3/PREP_STATUS.json"
CHART="$ROOT/packages/aiplat-ontology/chart/Chart.yaml"
DRILL_DIR="$ROOT/packages/aiplat-ontology/docs/a3/drills"
CMD="${1:-status}"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_REPO_ROOT="${AIPLAT_REPO_ROOT:-$ROOT}"
export AIPLAT_SPLIT_CHECKLIST="${AIPLAT_SPLIT_CHECKLIST:-$CHECKLIST}"
export AIPLAT_SPLIT_STATUS_JSON="${AIPLAT_SPLIT_STATUS_JSON:-$STATUS_JSON}"
export AIPLAT_SPLIT_CHART="${AIPLAT_SPLIT_CHART:-$CHART}"
export AIPLAT_LIVE_DRILL_DIR="${AIPLAT_LIVE_DRILL_DIR:-$DRILL_DIR}"
export AIPLAT_SPLIT_CMD="$CMD"
export AIPLAT_SPLIT_CAP="${AIPLAT_SPLIT_CAP:-ontology}"

"$PY" - <<'PY'
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
sys.path.insert(0, str(root / "scripts" / "lib"))
from aiplat_live_evidence import require_signed_live  # noqa: E402

checklist = Path(os.environ["AIPLAT_SPLIT_CHECKLIST"])
status_path = Path(os.environ["AIPLAT_SPLIT_STATUS_JSON"])
chart = Path(os.environ["AIPLAT_SPLIT_CHART"])
drill_dir = Path(os.environ["AIPLAT_LIVE_DRILL_DIR"])
cmd = os.environ["AIPLAT_SPLIT_CMD"]
cap = os.environ["AIPLAT_SPLIT_CAP"]

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
authorized_doc = "process_split_authorized: true" in text and "process_split_authorized: false" not in text
status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
status_flag = bool(status.get("process_split_authorized"))
chart_ok = chart.is_file() and 'aiplat.a3_process_split_authorized: "false"' in chart.read_text(encoding="utf-8")
live_ok, live_summary = require_signed_live(drill_dir)

report = {
    "gate": f"{cap}_a3_split_authorize",
    "checklist_marks": marks,
    "all_green": all_green,
    "live_evidence": live_summary,
    "live_production_signed": live_ok,
    "process_split_authorized_doc": authorized_doc,
    "process_split_authorized_status_json": status_flag,
    "chart_split_false_annotation": chart_ok,
    "ready_to_authorize": bool(all_green and live_ok and not authorized_doc),
}
print(json.dumps(report, ensure_ascii=False, indent=2))

if cmd == "status":
    sys.exit(0)
if cmd != "authorize":
    print("usage: a3_split_authorize.sh status|authorize", file=sys.stderr)
    sys.exit(2)

if not all_green:
    print(
        f"REFUSED: {cap} process_split_authorize — checklist not all ✅ (marks={marks}); 🟨≠authorize",
        file=sys.stderr,
    )
    sys.exit(1)
if not live_ok:
    print(
        f"REFUSED: {cap} process_split_authorize — need live-*.json with production_signed=true "
        f"(got={live_summary})",
        file=sys.stderr,
    )
    sys.exit(1)

text2 = text.replace("process_split_authorized: false", "process_split_authorized: true")
checklist.write_text(text2, encoding="utf-8")
status["process_split_authorized"] = True
status["live_evidence"] = live_summary
status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
if chart.is_file():
    c = chart.read_text(encoding="utf-8").replace(
        'aiplat.a3_process_split_authorized: "false"',
        'aiplat.a3_process_split_authorized: "true"',
    )
    chart.write_text(c, encoding="utf-8")
print(f"AUTHORIZED: {cap} process_split_authorized=true")
PY
