#!/usr/bin/env bash
# Aggregate five-products ops live / authorize status. READ-ONLY — never authorizes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

JSON_ONLY=0
[[ "${1:-}" == "--json" ]] && JSON_ONLY=1
if [[ "$JSON_ONLY" -eq 0 ]]; then
  echo "== Ops live status (read-only; does not authorize) ==" >&2
fi
export AIPLAT_OPS_LIVE_JSON_ONLY="$JSON_ONLY"

"$PY" - <<'PY'
import json, os, re, sys
from pathlib import Path

root = Path(".").resolve()
sys.path.insert(0, str(root / "scripts" / "lib"))
from aiplat_live_evidence import summarize_live_drills

def marks(checklist: Path):
    text = checklist.read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|.*\|\s*([✅🟨⬜])\s*\|", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out

def flag(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(data.get(key))

tracks = [
    {
        "id": "pg_ha",
        "gate": "cutover_authorized",
        "checklist": root / "packages/aiplat-central/docs/pg_ha/CUTOVER_CHECKLIST.md",
        "status_json": root / "packages/aiplat-central/docs/pg_ha/PREP_STATUS.json",
        "drill_dir": root / "packages/aiplat-central/docs/pg_ha/drills",
        "flag_key": "cutover_authorized",
        "authorize": "packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh",
        "live_doc": "packages/aiplat-central/docs/pg_ha/LIVE_DRILL_EVIDENCE.md",
    },
    {
        "id": "ontology_a3",
        "gate": "process_split_authorized",
        "checklist": root / "packages/aiplat-ontology/docs/a3/SPLIT_CHECKLIST.md",
        "status_json": root / "packages/aiplat-ontology/docs/a3/PREP_STATUS.json",
        "drill_dir": root / "packages/aiplat-ontology/docs/a3/drills",
        "flag_key": "process_split_authorized",
        "authorize": "packages/aiplat-ontology/scripts/a3_split_authorize.sh",
        "live_doc": "packages/aiplat-ontology/docs/a3/LIVE_DRILL_EVIDENCE.md",
    },
    {
        "id": "evaluation_a3",
        "gate": "process_split_authorized",
        "checklist": root / "packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md",
        "status_json": root / "packages/aiplat-evaluation/docs/a3/PREP_STATUS.json",
        "drill_dir": root / "packages/aiplat-evaluation/docs/a3/drills",
        "flag_key": "process_split_authorized",
        "authorize": "packages/aiplat-evaluation/scripts/a3_split_authorize.sh",
        "live_doc": "packages/aiplat-evaluation/docs/a3/LIVE_DRILL_EVIDENCE.md",
    },
    {
        "id": "pi_d3",
        "gate": "d3_production_authorized",
        "checklist": root / "packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md",
        "status_json": root / "packages/aiplat-pi-runtime/docs/d3/PREP_STATUS.json",
        "drill_dir": root / "packages/aiplat-pi-runtime/docs/d3/drills",
        "flag_key": "d3_production_authorized",
        "authorize": "packages/aiplat-pi-runtime/scripts/d3_authorize.sh",
        "live_doc": "packages/aiplat-pi-runtime/docs/d3/LIVE_DRILL_EVIDENCE.md",
    },
]

rows = []
any_authorized = False
for t in tracks:
    m = marks(t["checklist"]) if t["checklist"].is_file() else {}
    authorized = flag(t["status_json"], t["flag_key"])
    cl_text = t["checklist"].read_text(encoding="utf-8") if t["checklist"].is_file() else ""
    if f"{t['flag_key']}: true" in cl_text or f"{t['flag_key']}:true" in cl_text:
        authorized = True
    any_authorized = any_authorized or authorized
    all_green = bool(m) and all(v == "✅" for v in m.values())
    live = summarize_live_drills(t["drill_dir"])
    live_ok = bool(live.get("production_signed"))
    rows.append({
        "track": t["id"],
        "gate": t["gate"],
        "marks": m,
        "all_green": all_green,
        "live_production_signed": live_ok,
        "live_evidence": live,
        "authorized": authorized,
        "ready_to_authorize": bool(all_green and live_ok and not authorized),
        "authorize_script": t["authorize"],
        "live_doc": t["live_doc"],
    })

summary = {
    "kind": "ops_live_status",
    "schema_version": "aiplat.ops.live_status.v0",
    "read_only": True,
    "does_not_authorize": True,
    "tracks": rows,
    "any_gate_authorized": any_authorized,
    "runbook": "reports/five-products/OPS_LIVE_RUNBOOK.md",
}
print(json.dumps(summary, indent=2, ensure_ascii=False))

json_only = os.environ.get("AIPLAT_OPS_LIVE_JSON_ONLY") == "1"
if not json_only:
    print("\n-- summary --", file=sys.stderr)
    for r in rows:
        marks_s = "".join(f"{k}{v}" for k, v in sorted(r["marks"].items(), key=lambda x: int(x[0])))
        print(
            f"{r['track']}: authorized={r['authorized']} all_green={r['all_green']} "
            f"live_signed={r['live_production_signed']} ready={r['ready_to_authorize']} "
            f"marks={marks_s or '(none)'}",
            file=sys.stderr,
        )
    if any_authorized:
        print("NOTE: at least one gate reports authorized — verify intentional", file=sys.stderr)
    else:
        print("OK: all hard gates still unauthorized", file=sys.stderr)
PY

if [[ "$JSON_ONLY" -eq 1 ]]; then
  exit 0
fi

# Surface authorize status JSON from each script (status only)
for s in \
  packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh \
  packages/aiplat-ontology/scripts/a3_split_authorize.sh \
  packages/aiplat-evaluation/scripts/a3_split_authorize.sh \
  packages/aiplat-pi-runtime/scripts/d3_authorize.sh
do
  echo "== $s status ==" >&2
  bash "$s" status
done

echo "PASS: ops_live_status (read-only)" >&2
echo "See reports/five-products/OPS_LIVE_RUNBOOK.md" >&2
