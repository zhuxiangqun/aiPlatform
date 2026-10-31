#!/usr/bin/env bash
# PG/HA prep check — auto items for cutover checklist; NEVER sets cutover_authorized=true.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
OUT_DIR="$ROOT/packages/aiplat-central/docs/pg_ha"
STATUS_JSON="$OUT_DIR/PREP_STATUS.json"
DRILL_DIR="$OUT_DIR/drills"
mkdir -p "$DRILL_DIR"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_REPO_ROOT="$ROOT"
export AIPLAT_PG_HA_STATUS_JSON="$STATUS_JSON"
export AIPLAT_PG_HA_DRILL_DIR="$DRILL_DIR"

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
status_path = Path(os.environ["AIPLAT_PG_HA_STATUS_JSON"])
drill_dir = Path(os.environ["AIPLAT_PG_HA_DRILL_DIR"])
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

results: dict = {
    "schema_version": "aiplat.pg_ha.prep.v0",
    "checked_at": now,
    "cutover_authorized": False,
    "items": {},
}

def ok(item: str, detail: str) -> None:
    results["items"][item] = {"ok": True, "detail": detail}

def fail(item: str, detail: str) -> None:
    results["items"][item] = {"ok": False, "detail": detail}

# --- #5 contract coupling: platform apps must not import core.harness ---
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
        if re.search(r"(from|import)\s+core\.harness\b", text):
            bad.append(str(p.relative_to(root)))
if bad:
    fail("5_contract_coupling", f"core.harness imports in platform apps: {bad[:5]}")
else:
    ok("5_contract_coupling", "no core.harness imports under aiPlat-platform/apps")

# --- #6 chart / release cadence stub ---
chart = root / "packages" / "aiplat-central" / "chart" / "Chart.yaml"
values = root / "packages" / "aiplat-central" / "chart" / "values.yaml"
if chart.is_file() and values.is_file():
    txt = chart.read_text(encoding="utf-8")
    if 'aiplat.pg_ha_cutover_authorized: "false"' in txt or "cutover_authorized: \"false\"" in txt:
        ok("6_chart_release", f"chart skeleton present ({chart.relative_to(root)}); cutover=false annotated")
    else:
        ok("6_chart_release", f"chart skeleton present ({chart.relative_to(root)})")
else:
    fail("6_chart_release", "missing packages/aiplat-central/chart")

# --- runbooks present ---
for name in ("MIGRATION.md", "BACKUP_RESTORE.md", "HA.md", "ROLLBACK.md", "CUTOVER_CHECKLIST.md"):
    p = root / "packages" / "aiplat-central" / "docs" / "pg_ha" / name
    key = f"runbook_{name}"
    if p.is_file():
        ok(key, "present")
    else:
        fail(key, "missing")

# --- #1 identity/MFA unit smoke (narrow; not full OIDC E2E) ---
try:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "aiPlat-platform/tests/test_mfa.py", "-q", "--tb=line"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode == 0:
        ok("1_identity_mfa_unit", "test_mfa.py passed (admin MFA gate)")
    else:
        fail("1_identity_mfa_unit", (r.stdout or "")[-400:] + (r.stderr or "")[-200:])
except Exception as e:
    fail("1_identity_mfa_unit", str(e))

# --- tabletop drill log (does NOT authorize cutover) ---
drill = {
    "kind": "tabletop",
    "at": now,
    "note": "Automated prep check only. Migration/HA/backup live drills still required.",
    "migration_live": False,
    "backup_restore_live": False,
    "ha_failover_live": False,
    "rollback_live": False,
}
drill_path = drill_dir / f"tabletop-{now.replace(':', '')}.json"
drill_path.write_text(json.dumps(drill, indent=2) + "\n", encoding="utf-8")
ok("tabletop_log", str(drill_path.relative_to(root)))

# --- local rehearsal artifacts (🟨 only; never live PG/HA green) ---
sqlite_rehs = sorted(drill_dir.glob("sqlite-rehearsal-*.json"))
pg_rehs = sorted(drill_dir.glob("pg-rehearsal-*.json"))
ha_rehs = sorted(drill_dir.glob("ha-rehearsal-*.json"))
if sqlite_rehs:
    ok("3_backup_sqlite_rehearsal", str(sqlite_rehs[-1].relative_to(root)))
    ok("7_rollback_sqlite_rehearsal", str(sqlite_rehs[-1].relative_to(root)))
else:
    fail("3_backup_sqlite_rehearsal", "run packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh")
    fail("7_rollback_sqlite_rehearsal", "run packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh")
if pg_rehs:
    ok("2_pg_schema_rehearsal", str(pg_rehs[-1].relative_to(root)))
else:
    results["items"]["2_pg_schema_rehearsal"] = {
        "ok": False,
        "detail": "optional; AIPLAT_PG_DSN+psql/pg_dump or docker (pg_ha_local_rehearsal)",
    }
if ha_rehs:
    ok("4_ha_failover_local_rehearsal", str(ha_rehs[-1].relative_to(root)))
else:
    results["items"]["4_ha_failover_local_rehearsal"] = {
        "ok": False,
        "detail": "optional; run pg_ha_ha_failover_rehearsal.sh (needs docker)",
    }
live_rehs = sorted(drill_dir.glob("live-*.json"))
if live_rehs:
    ok("live_drill_evidence_present", str(live_rehs[-1].relative_to(root)))
else:
    results["items"]["live_drill_evidence_present"] = {
        "ok": False,
        "detail": "optional; see docs/pg_ha/LIVE_DRILL_EVIDENCE.md + pg_ha_record_live_drill.sh",
    }

# Never authorize
results["cutover_authorized"] = False
auto_green = all(
    results["items"].get(k, {}).get("ok")
    for k in ("5_contract_coupling", "6_chart_release", "1_identity_mfa_unit")
)
local_reh = all(
    results["items"].get(k, {}).get("ok")
    for k in ("3_backup_sqlite_rehearsal", "7_rollback_sqlite_rehearsal")
)
results["auto_prep_green"] = bool(auto_green)
results["local_rehearsal_green"] = bool(local_reh)
results["manual_still_required"] = [
    "2_pg_migration_live_drill",
    "3_backup_restore_live_drill",
    "4_ha_failover_live_drill",
    "7_rollback_live_drill",
    "1_oidc_full_regression",  # beyond MFA unit
]

status_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({
    "auto_prep_green": results["auto_prep_green"],
    "local_rehearsal_green": results["local_rehearsal_green"],
    "cutover_authorized": False,
    "status": str(status_path.relative_to(root)),
    "failed": [k for k, v in results["items"].items() if not v.get("ok")],
}, ensure_ascii=False, indent=2))

if not results["auto_prep_green"]:
    sys.exit(1)
# Gate expects rehearsal first; warn but do not fail prep_check alone
if not results["local_rehearsal_green"]:
    print("WARN: local SQLite rehearsal missing — run pg_ha_local_rehearsal.sh (five_products_gate does this)")
print("OK pg_ha_prep_check (cutover still unauthorized)")
PY

# Refresh checklist markdown checkmarks for auto items only
CHECKLIST="$OUT_DIR/CUTOVER_CHECKLIST.md"
"$PY" - <<'PY'
from pathlib import Path
import json, os
root = Path(os.environ["AIPLAT_REPO_ROOT"])
status = json.loads(Path(os.environ["AIPLAT_PG_HA_STATUS_JSON"]).read_text(encoding="utf-8"))
path = root / "packages/aiplat-central/docs/pg_ha/CUTOVER_CHECKLIST.md"
text = path.read_text(encoding="utf-8")
# Item 5 / 6
if status["items"].get("5_contract_coupling", {}).get("ok"):
    text = text.replace("| 5 | 契约耦合确认（无跨库直读） | 架构 | ⬜ |", "| 5 | 契约耦合确认（无跨库直读） | 架构 | ✅ |")
if status["items"].get("6_chart_release", {}).get("ok"):
    text = text.replace("| 6 | Chart / 发布节奏独立 | 运维 | ⬜ |", "| 6 | Chart / 发布节奏独立 | 运维 | ✅ |")
if status["items"].get("1_identity_mfa_unit", {}).get("ok"):
    text = text.replace("| 1 | 租户/OIDC 回归绿 | 平台 | ⬜ |", "| 1 | 租户/OIDC 回归绿 | 平台 | 🟨 |")
# Local SQLite rehearsal → 🟨 only (never ✅ until production-like PG drills)
if status["items"].get("3_backup_sqlite_rehearsal", {}).get("ok"):
    text = text.replace("| 3 | 备份恢复演练记录 | 运维 | ⬜ |", "| 3 | 备份恢复演练记录 | 运维 | 🟨 |")
if status["items"].get("7_rollback_sqlite_rehearsal", {}).get("ok"):
    text = text.replace("| 7 | 回滚演练一次 | 运维 | ⬜ |", "| 7 | 回滚演练一次 | 运维 | 🟨 |")
if status["items"].get("2_pg_schema_rehearsal", {}).get("ok"):
    text = text.replace("| 2 | PG 迁移演练记录（环境/日期/结果） | 运维 | ⬜ |", "| 2 | PG 迁移演练记录（环境/日期/结果） | 运维 | 🟨 |")
if status["items"].get("4_ha_failover_local_rehearsal", {}).get("ok"):
    text = text.replace("| 4 | HA failover + 回切演练记录 | 运维 | ⬜ |", "| 4 | HA failover + 回切演练记录 | 运维 | 🟨 |")
# keep cutover false
if "cutover_authorized: false" not in text:
    text = text.rstrip() + "\n\n`cutover_authorized: false`\n"
path.write_text(text, encoding="utf-8")
print("OK checklist refreshed (auto items only; cutover still false)")
PY
