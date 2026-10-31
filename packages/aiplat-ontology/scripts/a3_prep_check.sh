#!/usr/bin/env bash
# Ontology A3 prep — NEVER sets process_split_authorized=true; does NOT Accept ADR.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
OUT_DIR="$ROOT/packages/aiplat-ontology/docs/a3"
STATUS_JSON="$OUT_DIR/PREP_STATUS.json"
mkdir -p "$OUT_DIR"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_REPO_ROOT="$ROOT"
export AIPLAT_A3_STATUS_JSON="$STATUS_JSON"
export AIPLAT_A3_CAPABILITY=ontology

"$PY" - <<'PY'
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
status_path = Path(os.environ["AIPLAT_A3_STATUS_JSON"])
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

results: dict = {
    "schema_version": "aiplat.ontology.a3.prep.v0",
    "capability_id": "ontology",
    "checked_at": now,
    "process_split_authorized": False,
    "adr_status": "accepted_conditional",
    "items": {},
}

def ok(item: str, detail: str) -> None:
    results["items"][item] = {"ok": True, "detail": detail}

def fail(item: str, detail: str) -> None:
    results["items"][item] = {"ok": False, "detail": detail}

# --- #2 chart skeleton ---
chart = root / "packages" / "aiplat-ontology" / "chart" / "Chart.yaml"
values = root / "packages" / "aiplat-ontology" / "chart" / "values.yaml"
if chart.is_file() and values.is_file():
    txt = chart.read_text(encoding="utf-8")
    if 'aiplat.a3_process_split_authorized: "false"' in txt:
        ok("2_chart_skeleton", f"{chart.relative_to(root)}; split=false")
    else:
        fail("2_chart_skeleton", "missing a3_process_split_authorized=false annotation")
else:
    fail("2_chart_skeleton", "missing packages/aiplat-ontology/chart")

# --- #4 no core.harness.knowledge in platform apps ---
apps = root / "aiPlat-platform" / "apps"
bad = []
if apps.is_dir():
    for p in apps.rglob("*.py"):
        if "/tests/" in str(p).replace("\\", "/"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if re.search(r"(from|import)\s+core\.harness\.knowledge\b", text):
            bad.append(str(p.relative_to(root)))
if bad:
    fail("4_no_harness_knowledge", f"imports: {bad[:5]}")
else:
    ok("4_no_harness_knowledge", "no core.harness.knowledge under aiPlat-platform/apps")

# --- runbooks ---
for name in ("SPLIT_CHECKLIST.md", "README.md"):
    p = root / "packages/aiplat-ontology/docs/a3" / name
    if p.is_file():
        ok(f"runbook_{name}", "present")
    else:
        fail(f"runbook_{name}", "missing")

# --- ADR Accepted（有条件）; draft kept as对照 ---
adr = root / "reports/five-products/ADR-ONTOLOGY-A3.md"
draft = root / "reports/five-products/ADR-DRAFT-ontology-a3.md"
if adr.is_file():
    body = adr.read_text(encoding="utf-8")
    if "Accepted（有条件）" in body and "SPLIT_CHECKLIST" in body:
        ok("6_adr_accept_cosign", str(adr.relative_to(root)))
    else:
        fail("6_adr_accept_cosign", "ADR-ONTOLOGY-A3 missing Accepted（有条件）/SPLIT_CHECKLIST")
else:
    fail("6_adr_accept_cosign", "missing ADR-ONTOLOGY-A3.md")
if draft.is_file():
    ok("adr_draft_对照", str(draft.relative_to(root)))
else:
    results["items"]["adr_draft_对照"] = {"ok": False, "detail": "optional对照 missing"}

# --- #1 contract / unit adapters ---
try:
    r = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "aiPlat-core/core/tests/unit/test_ontology_api_v0.py",
            "-q", "--tb=line",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode == 0:
        ok("1_ontology_api_unit", "test_ontology_api_v0.py passed")
    else:
        fail("1_ontology_api_unit", (r.stdout or "")[-400:] + (r.stderr or "")[-200:])
except Exception as e:
    fail("1_ontology_api_unit", str(e))

# --- local rehearsal artifacts (🟨 only) ---
drill_dir = root / "packages/aiplat-ontology/docs/a3/drills"
reh = sorted(drill_dir.glob("local-rehearsal-*.json")) if drill_dir.is_dir() else []
if reh:
    ok("3_local_dual_write_rehearsal", str(reh[-1].relative_to(root)))
    ok("5_local_rollback_rehearsal", str(reh[-1].relative_to(root)))
else:
    results["items"]["3_local_dual_write_rehearsal"] = {
        "ok": False,
        "detail": "run packages/aiplat-ontology/scripts/a3_local_rehearsal.sh",
    }
    results["items"]["5_local_rollback_rehearsal"] = {
        "ok": False,
        "detail": "run packages/aiplat-ontology/scripts/a3_local_rehearsal.sh",
    }

results["process_split_authorized"] = False
auto_green = all(
    results["items"].get(k, {}).get("ok")
    for k in (
        "2_chart_skeleton",
        "4_no_harness_knowledge",
        "1_ontology_api_unit",
        "6_adr_accept_cosign",
    )
)
local_reh = all(
    results["items"].get(k, {}).get("ok")
    for k in ("3_local_dual_write_rehearsal", "5_local_rollback_rehearsal")
)
results["auto_prep_green"] = bool(auto_green)
results["local_rehearsal_green"] = bool(local_reh)
results["manual_still_required"] = [
    "3_storage_migration_dual_write_live_drill",
    "5_rollback_to_cohost_live_drill",
]

status_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({
    "auto_prep_green": results["auto_prep_green"],
    "local_rehearsal_green": results["local_rehearsal_green"],
    "process_split_authorized": False,
    "adr_status": results["adr_status"],
    "status": str(status_path.relative_to(root)),
    "failed": [k for k, v in results["items"].items() if not v.get("ok")],
}, ensure_ascii=False, indent=2))

if not results["auto_prep_green"]:
    sys.exit(1)
if not results["local_rehearsal_green"]:
    print("WARN: local A3 rehearsal missing — run a3_local_rehearsal.sh (five_products_gate does this)")
print("OK ontology a3_prep_check (process split still unauthorized; ADR Accepted conditional)")
PY

"$PY" - <<'PY'
from pathlib import Path
import json, os
root = Path(os.environ["AIPLAT_REPO_ROOT"])
status = json.loads(Path(os.environ["AIPLAT_A3_STATUS_JSON"]).read_text(encoding="utf-8"))
path = root / "packages/aiplat-ontology/docs/a3/SPLIT_CHECKLIST.md"
text = path.read_text(encoding="utf-8")
if status["items"].get("1_ontology_api_unit", {}).get("ok"):
    text = text.replace("| 1 | `ontology.api.v0` + `/ontology/healthz` 契约回归 | 平台 | ⬜ |",
                        "| 1 | `ontology.api.v0` + `/ontology/healthz` 契约回归 | 平台 | 🟨 |")
if status["items"].get("2_chart_skeleton", {}).get("ok"):
    text = text.replace("| 2 | 独立 Chart / 安装前缀骨架 | 运维 | ⬜ |",
                        "| 2 | 独立 Chart / 安装前缀骨架 | 运维 | ✅ |")
if status["items"].get("4_no_harness_knowledge", {}).get("ok"):
    text = text.replace("| 4 | platform apps 零 `core.harness.knowledge` 直导 | 架构 | ⬜ |",
                        "| 4 | platform apps 零 `core.harness.knowledge` 直导 | 架构 | ✅ |")
if status["items"].get("3_local_dual_write_rehearsal", {}).get("ok"):
    text = text.replace("| 3 | 存储迁移/回填 + 双写或只读切换演练 | 运维 | ⬜ |",
                        "| 3 | 存储迁移/回填 + 双写或只读切换演练 | 运维 | 🟨 |")
if status["items"].get("5_local_rollback_rehearsal", {}).get("ok"):
    text = text.replace("| 5 | 回滚演练（切回共宿 D1） | 运维 | ⬜ |",
                        "| 5 | 回滚演练（切回共宿 D1） | 运维 | 🟨 |")
if status["items"].get("6_adr_accept_cosign", {}).get("ok"):
    text = text.replace("| 6 | ADR Accepted 联签 | 架构 | ⬜ |",
                        "| 6 | ADR Accepted 联签 | 架构 | ✅ |")
if "process_split_authorized: false" not in text:
    text = text.rstrip() + "\n\n`process_split_authorized: false`\n"
path.write_text(text, encoding="utf-8")
print("OK ontology SPLIT_CHECKLIST refreshed")
PY
