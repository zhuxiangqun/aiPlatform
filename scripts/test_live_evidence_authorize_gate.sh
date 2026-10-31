#!/usr/bin/env bash
# Regression: authorize dual hard gate (checklist ✅ + production_signed live).
# Uses temp dirs only — never mutates package checklists/charts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/aiplat-live-gate.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

mkdir -p "$TMP/drills"
cat >"$TMP/CUTOVER_CHECKLIST.md" <<'EOF'
# temp

| # | 项 | Owner | Done |
|---|----|-------|:----:|
| 1 | a | ops | ✅ |
| 2 | b | ops | ✅ |

`cutover_authorized: false`
EOF
cat >"$TMP/PREP_STATUS.json" <<'EOF'
{"cutover_authorized": false}
EOF
cat >"$TMP/Chart.yaml" <<'EOF'
annotations:
  aiplat.pg_ha_cutover_authorized: "false"
EOF
cat >"$TMP/drills/live-unsigned.json" <<'EOF'
{
  "kind": "pg_ha_live_drill_evidence",
  "drill_id": "temp-unsigned",
  "production_signed": false
}
EOF

export AIPLAT_REPO_ROOT="$ROOT"
export AIPLAT_CUTOVER_CHECKLIST="$TMP/CUTOVER_CHECKLIST.md"
export AIPLAT_CUTOVER_STATUS_JSON="$TMP/PREP_STATUS.json"
export AIPLAT_CUTOVER_CHART="$TMP/Chart.yaml"
export AIPLAT_LIVE_DRILL_DIR="$TMP/drills"

echo "== case1: all ✅ + unsigned live → REFUSE =="
set +e
out1="$(bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize 2>&1)"
rc1=$?
set -e
[[ "$rc1" -ne 0 ]] || { echo "FAIL: expected REFUSE for unsigned live" >&2; echo "$out1" >&2; exit 1; }
echo "$out1" | grep -q 'production_signed=true' \
  || { echo "FAIL: refuse message must mention production_signed" >&2; echo "$out1" >&2; exit 1; }
grep -q 'cutover_authorized: false' "$TMP/CUTOVER_CHECKLIST.md"

echo "== case2a: all ✅ + signed but environment=local → REFUSE =="
"$PY" - <<PY
import json
from pathlib import Path
p = Path("$TMP/drills/live-unsigned.json")
d = json.loads(p.read_text())
d["production_signed"] = True
d["environment"] = "local"
d["drill_id"] = "temp-local-fake"
p.write_text(json.dumps(d) + "\n")
p.rename(Path("$TMP/drills/live-local-fake.json"))
PY
set +e
out2a="$(bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize 2>&1)"
rc2a=$?
set -e
[[ "$rc2a" -ne 0 ]] || { echo "FAIL: local env must not authorize" >&2; echo "$out2a" >&2; exit 1; }
grep -q 'cutover_authorized: false' "$TMP/CUTOVER_CHECKLIST.md"

echo "== case2: all ✅ + signed staging live → AUTHORIZE (temp only) =="
"$PY" - <<PY
import json
from pathlib import Path
# remove local fake so staging file is latest
Path("$TMP/drills/live-local-fake.json").unlink(missing_ok=True)
p = Path("$TMP/drills/live-signed.json")
d = {
  "kind": "pg_ha_live_drill_evidence",
  "drill_id": "temp-signed",
  "environment": "staging",
  "production_signed": True,
}
p.write_text(json.dumps(d) + "\n")
PY
bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize
grep -q 'cutover_authorized: true' "$TMP/CUTOVER_CHECKLIST.md"
grep -q 'aiplat.pg_ha_cutover_authorized: "true"' "$TMP/Chart.yaml"
"$PY" -c "import json; assert json.load(open('$TMP/PREP_STATUS.json'))['cutover_authorized'] is True"

echo "== case3: helper unit =="
"$PY" - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "scripts/lib")
from aiplat_live_evidence import require_signed_live, summarize_live_drills
ok, s = require_signed_live(Path("packages/aiplat-pi-runtime/docs/d3/drills"))
assert ok is False
assert s["required_for_authorize"] is True
print("OK helper against real drills (unsigned/absent)")
PY

# Ensure real package gates untouched
grep -q 'cutover_authorized: false' packages/aiplat-central/docs/pg_ha/CUTOVER_CHECKLIST.md
grep -q 'aiplat.pg_ha_cutover_authorized: "false"' packages/aiplat-central/chart/Chart.yaml
grep -q 'd3_production_authorized: false' packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md

echo "PASS: test_live_evidence_authorize_gate (temp only; package gates still false)"
