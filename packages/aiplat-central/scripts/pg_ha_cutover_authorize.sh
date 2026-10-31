#!/usr/bin/env bash
# PG/HA cutover authorize gate.
# status   — report readiness (exit 0); never mutates
# authorize — set cutover_authorized=true ONLY if checklist all ✅; else REFUSE
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
CHECKLIST="$ROOT/packages/aiplat-central/docs/pg_ha/CUTOVER_CHECKLIST.md"
STATUS_JSON="$ROOT/packages/aiplat-central/docs/pg_ha/PREP_STATUS.json"
CHART="$ROOT/packages/aiplat-central/chart/Chart.yaml"
DRILL_DIR="$ROOT/packages/aiplat-central/docs/pg_ha/drills"
CMD="${1:-status}"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_REPO_ROOT="${AIPLAT_REPO_ROOT:-$ROOT}"
# Allow test overrides (temp dirs); default to package paths.
export AIPLAT_CUTOVER_CHECKLIST="${AIPLAT_CUTOVER_CHECKLIST:-$CHECKLIST}"
export AIPLAT_CUTOVER_STATUS_JSON="${AIPLAT_CUTOVER_STATUS_JSON:-$STATUS_JSON}"
export AIPLAT_CUTOVER_CHART="${AIPLAT_CUTOVER_CHART:-$CHART}"
export AIPLAT_LIVE_DRILL_DIR="${AIPLAT_LIVE_DRILL_DIR:-$DRILL_DIR}"
export AIPLAT_CUTOVER_CMD="$CMD"

"$PY" - <<'PY'
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
sys.path.insert(0, str(root / "scripts" / "lib"))
from aiplat_live_evidence import require_signed_live  # noqa: E402

checklist = Path(os.environ["AIPLAT_CUTOVER_CHECKLIST"])
status_path = Path(os.environ["AIPLAT_CUTOVER_STATUS_JSON"])
chart = Path(os.environ["AIPLAT_CUTOVER_CHART"])
drill_dir = Path(os.environ["AIPLAT_LIVE_DRILL_DIR"])
cmd = os.environ["AIPLAT_CUTOVER_CMD"]

text = checklist.read_text(encoding="utf-8")
rows = []
for line in text.splitlines():
    m = re.match(r"^\|\s*(\d+)\s*\|.*\|\s*([✅🟨⬜])\s*\|", line)
    if m:
        rows.append((int(m.group(1)), m.group(2)))
if not rows:
    print("FAIL: no checklist rows parsed", file=sys.stderr)
    sys.exit(2)

all_green = all(mark == "✅" for _, mark in rows)
marks = {n: m for n, m in rows}
authorized_doc = "cutover_authorized: true" in text and "cutover_authorized: false" not in text

status = {}
if status_path.is_file():
    status = json.loads(status_path.read_text(encoding="utf-8"))
status_flag = bool(status.get("cutover_authorized"))

chart_ok = False
if chart.is_file():
    chart_ok = 'aiplat.pg_ha_cutover_authorized: "false"' in chart.read_text(encoding="utf-8")

live_ok, live_summary = require_signed_live(drill_dir)

report = {
    "gate": "pg_ha_cutover_authorize",
    "checklist_marks": marks,
    "all_green": all_green,
    "live_evidence": live_summary,
    "live_production_signed": live_ok,
    "cutover_authorized_doc": authorized_doc,
    "cutover_authorized_status_json": status_flag,
    "chart_cutover_false_annotation": chart_ok,
    "ready_to_authorize": bool(all_green and live_ok and not authorized_doc),
}
print(json.dumps(report, ensure_ascii=False, indent=2))

if cmd == "status":
    sys.exit(0)

if cmd != "authorize":
    print("usage: pg_ha_cutover_authorize.sh status|authorize", file=sys.stderr)
    sys.exit(2)

if not all_green:
    print(
        "REFUSED: cutover_authorize — checklist not all ✅ "
        f"(marks={marks}); 🟨≠authorize",
        file=sys.stderr,
    )
    sys.exit(1)

if not live_ok:
    print(
        "REFUSED: cutover_authorize — need live-*.json with production_signed=true "
        f"(see LIVE_DRILL_EVIDENCE.md); got={live_summary}",
        file=sys.stderr,
    )
    sys.exit(1)

text2 = text.replace("cutover_authorized: false", "cutover_authorized: true")
checklist.write_text(text2, encoding="utf-8")
status["cutover_authorized"] = True
status["authorized_at_note"] = "authorized by pg_ha_cutover_authorize.sh after all ✅ + signed live"
status["live_evidence"] = live_summary
status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
if chart.is_file():
    c = chart.read_text(encoding="utf-8")
    c = c.replace(
        'aiplat.pg_ha_cutover_authorized: "false"',
        'aiplat.pg_ha_cutover_authorized: "true"',
    )
    chart.write_text(c, encoding="utf-8")
print("AUTHORIZED: cutover_authorized=true")
PY
