#!/usr/bin/env bash
# All five capabilities — D3 local acceptance (UAT dry-run).
# Explicitly unfrozen 2026-11-01. Never authorize / production_signed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CLOSEOUT="$ROOT/reports/five-products/ops/D3_LOCAL_ACCEPTANCE.md"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== D3 local acceptance ALL (environment=local; does NOT authorize) =="

bash packages/aiplat-central/scripts/d3_local_acceptance.sh || fail "central"
bash packages/aiplat-fde/scripts/d3_local_acceptance.sh || fail "fde"
bash packages/aiplat-ontology/scripts/d3_local_acceptance.sh || fail "ontology"
bash packages/aiplat-evaluation/scripts/d3_local_acceptance.sh || fail "evaluation"
bash packages/aiplat-diagnosis/scripts/d3_local_acceptance.sh || fail "diagnosis"
# Pi last — starts HTTP listeners
bash packages/aiplat-pi-runtime/scripts/d3_local_acceptance.sh || fail "pi"

cat >"$CLOSEOUT" <<EOF
# D3 Local Acceptance (five + diagnosis)

- recorded_at: \`$STAMP\`
- environment: \`local\`
- result: **PASS**
- production_signed: **false**
- authorize: **not attempted / REFUSE paths covered per pack**

## Commands

\`\`\`bash
bash scripts/ops_d3_local_acceptance_all.sh
\`\`\`

## Unfreeze

See [\`ENGINEERING_UNFREEZE_D3_E2E.md\`](./ENGINEERING_UNFREEZE_D3_E2E.md).
EOF

pass "ops_d3_local_acceptance_all → $CLOSEOUT"
