#!/usr/bin/env bash
# Pi D3 prep check — NEVER sets d3_production_authorized=true.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
OUT_DIR="$ROOT/packages/aiplat-pi-runtime/docs/d3"
STATUS_JSON="$OUT_DIR/PREP_STATUS.json"
mkdir -p "$OUT_DIR" "$OUT_DIR/drills"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_REPO_ROOT="$ROOT"
export AIPLAT_D3_STATUS_JSON="$STATUS_JSON"

"$PY" - <<'PY'
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(os.environ["AIPLAT_REPO_ROOT"])
status_path = Path(os.environ["AIPLAT_D3_STATUS_JSON"])
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
results = {
    "schema_version": "aiplat.pi.d3.prep.v0",
    "capability_id": "pi",
    "checked_at": now,
    "d3_production_authorized": False,
    "adr_status": "accepted_conditional",
    "items": {},
}

def ok(k, d): results["items"][k] = {"ok": True, "detail": d}
def fail(k, d): results["items"][k] = {"ok": False, "detail": d}

# #1 D2 admin
r = subprocess.run(
    ["bash", str(root / "packages/aiplat-pi-runtime/scripts/d2_admin_check.sh")],
    cwd=str(root), capture_output=True, text=True, timeout=120,
)
if r.returncode == 0:
    ok("1_d2_admin", "d2_admin_check passed")
else:
    fail("1_d2_admin", (r.stdout or "")[-300:] + (r.stderr or "")[-200:])

# #2 chart + docs
chart = root / "packages/aiplat-pi-runtime/chart/Chart.yaml"
if chart.is_file() and 'aiplat.d3_production_authorized: "false"' in chart.read_text(encoding="utf-8"):
    ok("2_chart_docs", "chart d3_production_authorized=false")
else:
    fail("2_chart_docs", "missing chart annotation")
for name in ("D3_CHECKLIST.md", "README.md", "BUNDLE_INTEGRITY.md", "OPS_SURFACE.md"):
    p = root / "packages/aiplat-pi-runtime/docs/d3" / name
    ok(f"runbook_{name}", "present") if p.is_file() else fail(f"runbook_{name}", "missing")

# #7 enterprise default 0
inst = (root / "packages/aiplat-pi-runtime/scripts/d1_install.sh").read_text(encoding="utf-8")
if "AIPLAT_ENTERPRISE=0" in inst:
    ok("7_enterprise_default_off", "d1_install AIPLAT_ENTERPRISE=0")
else:
    fail("7_enterprise_default_off", "missing")

# #8 ADR
adr = root / "reports/five-products/ADR-PI-D3.md"
if adr.is_file() and "Accepted（有条件）" in adr.read_text(encoding="utf-8") and "D3_CHECKLIST" in adr.read_text(encoding="utf-8"):
    ok("8_adr_accept_cosign", str(adr.relative_to(root)))
else:
    fail("8_adr_accept_cosign", "missing ADR-PI-D3 Accepted（有条件）")

# local rehearsal
drill_dir = root / "packages/aiplat-pi-runtime/docs/d3/drills"
reh = sorted(drill_dir.glob("local-rehearsal-*.json")) if drill_dir.is_dir() else []
if reh:
    ok("3_bundle_local_rehearsal", str(reh[-1].relative_to(root)))
    ok("4_ops_docs", "OPS_SURFACE.md + local reh")
    ok("6_rollback_local_rehearsal", str(reh[-1].relative_to(root)))
else:
    for k in ("3_bundle_local_rehearsal", "4_ops_docs", "6_rollback_local_rehearsal"):
        results["items"][k] = {"ok": False, "detail": "run d3_local_rehearsal.sh"}
soc = sorted(drill_dir.glob("soc-rehearsal-*.json")) if drill_dir.is_dir() else []
if soc:
    ok("5_soc_local_rehearsal", str(soc[-1].relative_to(root)))
else:
    results["items"]["5_soc_local_rehearsal"] = {
        "ok": False,
        "detail": "run d3_soc_local_rehearsal.sh (file sink only)",
    }
live = sorted(drill_dir.glob("live-*.json")) if drill_dir.is_dir() else []
if live:
    ok("live_drill_evidence_present", str(live[-1].relative_to(root)))
else:
    results["items"]["live_drill_evidence_present"] = {
        "ok": False,
        "detail": "optional; docs/d3/LIVE_DRILL_EVIDENCE.md + d3_record_live_drill.sh",
    }

results["d3_production_authorized"] = False
auto = all(results["items"].get(k, {}).get("ok") for k in ("1_d2_admin", "2_chart_docs", "7_enterprise_default_off", "8_adr_accept_cosign"))
local = all(
    results["items"].get(k, {}).get("ok")
    for k in ("3_bundle_local_rehearsal", "6_rollback_local_rehearsal", "5_soc_local_rehearsal")
)
results["auto_prep_green"] = bool(auto)
results["local_rehearsal_green"] = bool(local)
results["manual_still_required"] = ["5_soc_live_drill", "3_4_6_production_signoff"]

status_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({
    "auto_prep_green": results["auto_prep_green"],
    "local_rehearsal_green": results["local_rehearsal_green"],
    "d3_production_authorized": False,
    "adr_status": "accepted_conditional",
    "failed": [k for k, v in results["items"].items() if not v.get("ok")],
}, ensure_ascii=False, indent=2))
if not results["auto_prep_green"]:
    sys.exit(1)
if not results["local_rehearsal_green"]:
    print("WARN: run d3_local_rehearsal.sh (five_products_gate does this)")
print("OK pi d3_prep_check (d3 production still unauthorized)")
PY

"$PY" - <<'PY'
from pathlib import Path
import json, os
root = Path(os.environ["AIPLAT_REPO_ROOT"])
status = json.loads(Path(os.environ["AIPLAT_D3_STATUS_JSON"]).read_text(encoding="utf-8"))
path = root / "packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md"
text = path.read_text(encoding="utf-8")
if status["items"].get("1_d2_admin", {}).get("ok"):
    text = text.replace("| 1 | D2 admin pack 绿 | 平台 | ⬜ |", "| 1 | D2 admin pack 绿 | 平台 | ✅ |")
if status["items"].get("2_chart_docs", {}).get("ok"):
    text = text.replace("| 2 | D3 Chart / 文档骨架 | 运维 | ⬜ |", "| 2 | D3 Chart / 文档骨架 | 运维 | ✅ |")
if status["items"].get("3_bundle_local_rehearsal", {}).get("ok"):
    text = text.replace("| 3 | Bundle 完整性策略文档 + 本地校验演练 | 平台 | ⬜ |",
                        "| 3 | Bundle 完整性策略文档 + 本地校验演练 | 平台 | 🟨 |")
if status["items"].get("4_ops_docs", {}).get("ok"):
    text = text.replace("| 4 | 运维面 healthz/证据约定文档 | 平台 | ⬜ |",
                        "| 4 | 运维面 healthz/证据约定文档 | 平台 | 🟨 |")
if status["items"].get("6_rollback_local_rehearsal", {}).get("ok"):
    text = text.replace("| 6 | N-1 升级/回滚 live 或等价演练 | 运维 | ⬜ |",
                        "| 6 | N-1 升级/回滚 live 或等价演练 | 运维 | 🟨 |")
if status["items"].get("5_soc_local_rehearsal", {}).get("ok"):
    text = text.replace("| 5 | SOC/告警出口（enterprise opt-in）演练记录 | 运维 | ⬜ |",
                        "| 5 | SOC/告警出口（enterprise opt-in）演练记录 | 运维 | 🟨 |")
if status["items"].get("7_enterprise_default_off", {}).get("ok"):
    text = text.replace("| 7 | enterprise 默认仍 0（回归） | 平台 | ⬜ |",
                        "| 7 | enterprise 默认仍 0（回归） | 平台 | ✅ |")
if status["items"].get("8_adr_accept_cosign", {}).get("ok"):
    text = text.replace("| 8 | ADR Accepted 联签 | 架构 | ⬜ |",
                        "| 8 | ADR Accepted 联签 | 架构 | ✅ |")
if "d3_production_authorized: false" not in text:
    text = text.rstrip() + "\n\n`d3_production_authorized: false`\n"
path.write_text(text, encoding="utf-8")
print("OK D3_CHECKLIST refreshed")
PY
