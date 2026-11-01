#!/usr/bin/env bash
# Cross-capability local E2E: contracts → packs → slice (Bundle/Pi/FDE) → Onto/Eval smoke.
# Explicitly unfrozen 2026-11-01. environment=local only. Never authorize.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CLOSEOUT="$ROOT/reports/five-products/ops/FIVE_PRODUCTS_E2E_LOCAL.md"
EVID="$ROOT/reports/five-products/ops/evidence"
mkdir -p "$EVID"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== Five-products cross-capability E2E (local; does NOT authorize) =="
echo "stamp=$STAMP"

"$PY" scripts/check_five_products_status_sync.py || fail "STATUS sync"
bash scripts/check_five_products_packaging_surface.sh || fail "packaging"
bash scripts/check_five_products_perf_baseline.sh || fail "perf"
bash packages/aiplat-central/scripts/a2_version_check.sh || fail "a2"
bash packages/aiplat-central/scripts/d2_compat_check.sh || fail "compat"

# Slice: aiPlat home → Pi Thin → diagnosis → FDE acceptance bind
bash scripts/slice_e2e.sh --scenario lock-service || fail "slice_e2e positive"
bash scripts/slice_e2e.sh --scenario lock-service --inject disconnect || fail "slice_e2e disconnect"

# Cohost health contracts / smoke (lightweight)
bash packages/aiplat-ontology/scripts/d1_smoke.sh || fail "ontology smoke"
bash packages/aiplat-evaluation/scripts/d1_smoke.sh || fail "evaluation smoke"
bash packages/aiplat-fde/scripts/d1_smoke.sh || fail "fde smoke"

# Hard gates still refuse
if bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize; then
  fail "cutover authorize must REFUSE"
fi
if bash packages/aiplat-ontology/scripts/a3_split_authorize.sh authorize; then
  fail "ontology split must REFUSE"
fi
if bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize; then
  fail "evaluation split must REFUSE"
fi
if bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh authorize; then
  fail "pi d3 authorize must REFUSE"
fi
pass "all authorize REFUSED"

OUT="$EVID/local-five-products-e2e-${STAMP}.json"
"$PY" - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(json.dumps({
  "kind": "five_products_e2e_local",
  "at": "$STAMP",
  "environment": "local",
  "steps": [
    "status_sync", "packaging", "perf", "a2", "compat",
    "slice_e2e_lock_service", "slice_e2e_disconnect",
    "ontology_smoke", "evaluation_smoke", "fde_smoke",
    "authorize_refused"
  ],
  "production_signed": False,
  "staging_ready": False,
}, indent=2) + "\n")
print("OK wrote", r"""$OUT""")
PY

cat >"$CLOSEOUT" <<EOF
# Five-products cross-capability E2E (local)

- recorded_at: \`$STAMP\`
- environment: \`local\`
- result: **PASS**
- evidence: \`ops/evidence/$(basename "$OUT")\`
- production_signed: **false**
- staging_ready: **false**

## Flow covered

1. STATUS ↔ manifest  
2. Packaging + perf + A2/compat  
3. \`slice_e2e\` lock-service（Bundle → Pi Thin → FDE acceptance bind）  
4. \`slice_e2e --inject disconnect\` fail-closed  
5. Ontology / Evaluation / FDE D1 smoke  
6. 四轨 authorize **REFUSE**

## Commands

\`\`\`bash
bash scripts/ops_five_products_e2e_local.sh
\`\`\`

## Unfreeze

[\`ENGINEERING_UNFREEZE_D3_E2E.md\`](./ENGINEERING_UNFREEZE_D3_E2E.md) — authorize 仍冻结。
EOF

pass "ops_five_products_e2e_local → $CLOSEOUT"
