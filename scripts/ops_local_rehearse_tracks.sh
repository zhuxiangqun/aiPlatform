#!/usr/bin/env bash
# Local (non-authorize) rehearsal for Ontology/Eval A3 + Pi D3 (+ optional PG/HA).
# Writes local-*.json with local_signed; never production_signed / authorize.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="$ROOT/reports/five-products/ops/evidence"
RUNLOG="$ROOT/reports/five-products/ops/LOCAL_TRACKS_RUNLOG.md"
mkdir -p "$EVID_DIR"

INCLUDE_PGHA="${AIPLAT_LOCAL_INCLUDE_PGHA:-0}"
OPERATOR="${AIPLAT_LOCAL_DRILL_OPERATOR:-${USER:-ops}}"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== ops local rehearse tracks (environment=local; does not authorize) =="

# --- Ontology A3 ---
bash packages/aiplat-ontology/scripts/a3_local_rehearsal.sh || fail "ontology a3_local_rehearsal"
# contract sample as local healthz proxy
"$PY" reports/five-products/modules/ontology/contracts/validate_sample.py || fail "ontology validate_sample"
ITEMS="$(mktemp)"
cat >"$ITEMS" <<JSON
{
  "storage_migration": {"done": true, "evidence": "a3_local_rehearsal dual-write/file copy (local)"},
  "rollback_cohost": {"done": true, "evidence": "a3_local_rehearsal prefix rollback to cohost (local)"},
  "healthz_contract": {"done": true, "evidence": "modules/ontology/contracts/validate_sample.py (local schema; not live HTTP)"}
}
JSON
export AIPLAT_LOCAL_DRILL_ITEMS_FILE="$ITEMS"
export AIPLAT_LOCAL_DRILL_OPERATOR="$OPERATOR"
export AIPLAT_LOCAL_SIGN=1
export AIPLAT_LOCAL_DRILL_ID="ontology-a3-local-${STAMP}"
bash packages/aiplat-ontology/scripts/a3_record_local_drill.sh
ONT_LOCAL="$(ls -1t packages/aiplat-ontology/docs/a3/drills/local-ontology-a3-local-*.json | head -1)"
cp "$ONT_LOCAL" "$EVID_DIR/$(basename "$ONT_LOCAL")"
rm -f "$ITEMS"
bash packages/aiplat-ontology/scripts/a3_split_authorize.sh status >/dev/null
pass "ontology A3 local_signed (process_split still unauthorized)"

# --- Evaluation A3 ---
bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh || fail "evaluation a3_local_rehearsal"
"$PY" reports/five-products/modules/evaluation/contracts/validate_sample.py || fail "evaluation validate_sample"
ITEMS="$(mktemp)"
cat >"$ITEMS" <<JSON
{
  "backup_restore_rollback": {"done": true, "evidence": "a3_local_rehearsal sqlite dump/restore + cohost rollback (local)"},
  "healthz_protocol": {"done": true, "evidence": "modules/evaluation/contracts/validate_sample.py (local schema; not live HTTP)"}
}
JSON
export AIPLAT_LOCAL_DRILL_ITEMS_FILE="$ITEMS"
export AIPLAT_LOCAL_DRILL_ID="evaluation-a3-local-${STAMP}"
export AIPLAT_LOCAL_SIGN=1
bash packages/aiplat-evaluation/scripts/a3_record_local_drill.sh
EVAL_LOCAL="$(ls -1t packages/aiplat-evaluation/docs/a3/drills/local-evaluation-a3-local-*.json | head -1)"
cp "$EVAL_LOCAL" "$EVID_DIR/$(basename "$EVAL_LOCAL")"
rm -f "$ITEMS"
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status >/dev/null
pass "evaluation A3 local_signed (process_split still unauthorized)"

# --- Pi D3 ---
bash packages/aiplat-pi-runtime/scripts/d3_local_rehearsal.sh || fail "d3_local_rehearsal"
bash packages/aiplat-pi-runtime/scripts/d3_soc_local_rehearsal.sh || fail "d3_soc_local_rehearsal"
ITEMS="$(mktemp)"
cat >"$ITEMS" <<JSON
{
  "bundle_integrity": {"done": true, "evidence": "d3_local_rehearsal bundle checksum (local)"},
  "ops_surface": {"done": true, "evidence": "docs/d3/OPS_SURFACE.md + local rehearsal (local; not prod healthz SLA)"},
  "soc_alert_export": {"done": true, "evidence": "d3_soc_local_rehearsal file-sink (local; no external SOC)"},
  "n1_upgrade_rollback": {"done": true, "evidence": "d1_upgrade/rollback or d3_local_rehearsal N-1 path (local)"}
}
JSON
export AIPLAT_LOCAL_DRILL_ITEMS_FILE="$ITEMS"
export AIPLAT_LOCAL_DRILL_ID="pi-d3-local-${STAMP}"
export AIPLAT_LOCAL_SIGN=1
bash packages/aiplat-pi-runtime/scripts/d3_record_local_drill.sh
PI_LOCAL="$(ls -1t packages/aiplat-pi-runtime/docs/d3/drills/local-pi-d3-local-*.json | head -1)"
cp "$PI_LOCAL" "$EVID_DIR/$(basename "$PI_LOCAL")"
rm -f "$ITEMS"
bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh status >/dev/null
pass "pi D3 local_signed (d3_production still unauthorized)"

# --- Optional PG/HA (docker) ---
if [[ "$INCLUDE_PGHA" == "1" ]]; then
  bash packages/aiplat-central/scripts/pg_ha_local_staging.sh all || fail "pg_ha local staging"
  PG_LOCAL="$(ls -1t packages/aiplat-central/docs/pg_ha/drills/local-pgha-local-*.json | head -1 || true)"
  [[ -n "$PG_LOCAL" ]] && cp "$PG_LOCAL" "$EVID_DIR/$(basename "$PG_LOCAL")"
fi

# Aggregate status (local only)
export PYTHONPATH="$ROOT/scripts/lib${PYTHONPATH:+:$PYTHONPATH}"
"$PY" - <<PY
import json
from pathlib import Path
from aiplat_local_drill import summarize_local

root = Path(".")
tracks = [
    ("pg_ha", root / "packages/aiplat-central/docs/pg_ha/drills"),
    ("ontology_a3", root / "packages/aiplat-ontology/docs/a3/drills"),
    ("evaluation_a3", root / "packages/aiplat-evaluation/docs/a3/drills"),
    ("pi_d3", root / "packages/aiplat-pi-runtime/docs/d3/drills"),
]
rows = []
for name, d in tracks:
    s = summarize_local(d)
    rows.append((name, s))
    print(f"{name}: local_signed={s.get('local_signed')} latest={s.get('latest')}")

runlog = Path("$RUNLOG")
lines = [
    "# Local tracks runlog (non-authorize)",
    "",
    f"- recorded_at: \`$STAMP\`",
    f"- operator: \`$OPERATOR\`",
    "- environment: \`local\`",
    "- production_signed: **false** (all tracks)",
    "- authorize: **not attempted / not ready**",
    "",
    "| Track | local_signed | latest |",
    "|-------|:------------:|--------|",
]
for name, s in rows:
    latest = s.get("latest") or ""
    short = Path(latest).name if latest else "—"
    lines.append(f"| {name} | {str(s.get('local_signed')).lower()} | \`{short}\` |")
lines += [
    "",
    "## Notes",
    "",
    "- \`local_signed\` ≠ \`production_signed\`; checklist stays 🟨 for production.",
    "- Re-run: \`bash scripts/ops_local_rehearse_tracks.sh\`",
    "- PG/HA docker path: \`AIPLAT_LOCAL_INCLUDE_PGHA=1 bash scripts/ops_local_rehearse_tracks.sh\`",
    "",
]
runlog.write_text("\n".join(lines), encoding="utf-8")
print("OK wrote", runlog)
PY

# Hard gates must remain false
bash scripts/ops_live_status.sh --json | "$PY" -c '
import sys, json
d=json.load(sys.stdin)
for t in d["tracks"]:
    assert t["ready_to_authorize"] is False, t
    assert t["authorized"] is False, t
print("PASS: all tracks ready_to_authorize=false")
'
pass "ops_local_rehearse_tracks"
