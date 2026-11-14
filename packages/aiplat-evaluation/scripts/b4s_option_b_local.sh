#!/usr/bin/env bash
# Wire B4-S staging scaffold → Option B local rehearsal (≠ staging / ≠ Chart flip).
# Emits unsigned scaffold template, runs b4s_local_rehearsal on :5434, copies
# evidence into reports/five-products/ops/evidence/, asserts authorize locked.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PKG="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_OPS="$ROOT/reports/five-products/ops/evidence"
NOTE="$ROOT/reports/five-products/ops/OPTION_B_B4S_LAST_RUN.md"
mkdir -p "$EVID_OPS"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_EVAL_PYTHON="$PY"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== B4-S ↔ Option B local (environment=local; does NOT authorize) =="
echo "stamp=$STAMP py=$PY"

[[ -f "$ROOT/reports/five-products/ops/OPTION_B_LOCAL_VM.md" ]] || fail "missing OPTION_B_LOCAL_VM.md"
[[ -f "$PKG/docs/a3/B4S_STAGING_SCAFFOLD.md" ]] || fail "missing B4S_STAGING_SCAFFOLD.md"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  fail "docker required for B4-S Option B local (daemon down)"
fi

echo "== emit unsigned scaffold template =="
"$PY" "$PKG/scripts/b4s_staging_scaffold_emit.py" || fail "scaffold emit"

echo "== B4-S local rehearsal (dedicated PG :5434; leaves Option B :5433 alone) =="
bash "$PKG/scripts/b4s_local_rehearsal.sh" || fail "b4s_local_rehearsal"

LATEST="$(ls -1t "$PKG/docs/a3/drills"/local-eval-b4s-rehearsal-*.json 2>/dev/null | head -1 || true)"
[[ -n "$LATEST" && -f "$LATEST" ]] || fail "missing local-eval-b4s-rehearsal evidence"
cp "$LATEST" "$EVID_OPS/$(basename "$LATEST")"
pass "copied $(basename "$LATEST") → ops/evidence"

echo "== Chart still false =="
grep -q 'aiplat.a3_process_split_authorized: "false"' "$PKG/chart/Chart.yaml" \
  || fail "Chart annotation flipped unexpectedly"
bash "$PKG/scripts/a3_split_authorize.sh" status | "$PY" -c '
import json,sys
d=json.load(sys.stdin)
assert d.get("ready_to_authorize") is False
assert d.get("live_production_signed") is False
print("ready_to_authorize=false")
'

EVID_BASE="$(basename "$LATEST")"
cat >"$NOTE" <<EOF
# Option B · B4-S local last run

- recorded_at: \`$STAMP\`
- command: \`bash packages/aiplat-evaluation/scripts/b4s_option_b_local.sh\`
- result: **PASS**
- environment: \`local\`
- stack: B4-S compose PG \`:5434\` (sibling of Option B PGHA \`:5433\`)
- scaffold: [B4S_STAGING_SCAFFOLD.md](../../packages/aiplat-evaluation/docs/a3/B4S_STAGING_SCAFFOLD.md) · unfreeze \`draft_blocked\`
- evidence: \`$EVID_BASE\` (also under \`ops/evidence/\`)
- staging_ready: **false**
- production_signed: **false**
- Chart \`a3_process_split_authorized\`: **false**
- authorize: **not attempted** / \`ready_to_authorize=false\`

## Honesty

Option B local rehearsal ≠ independent staging host ≠ Chart flip.
EOF

pass "b4s_option_b_local ($STAMP)"
echo "NOTE: local only — do not claim staging; do not flip Chart."
