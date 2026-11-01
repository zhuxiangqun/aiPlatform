#!/usr/bin/env bash
# Engineering freeze gate — local packs complete; hard gates stay false.
# Does NOT set staging_ready. Does NOT authorize.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

echo "== Engineering freeze check (local only; does NOT authorize) =="

"$PY" scripts/check_five_products_status_sync.py || fail "STATUS sync"
bash scripts/check_five_products_packaging_surface.sh || fail "packaging surface"
bash scripts/check_five_products_perf_baseline.sh || fail "perf baseline"
bash packages/aiplat-central/scripts/a2_version_check.sh || fail "a2 version"
bash packages/aiplat-central/scripts/d2_compat_check.sh || fail "compat"
bash packages/aiplat-central/scripts/d2_security_check.sh || fail "security"

# Authorize must REFUSE on all four tracks
if bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize; then
  fail "cutover authorize must REFUSE"
fi
if bash packages/aiplat-ontology/scripts/a3_split_authorize.sh authorize; then
  fail "ontology split authorize must REFUSE"
fi
if bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize; then
  fail "evaluation split authorize must REFUSE"
fi
if bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh authorize; then
  fail "pi d3 authorize must REFUSE"
fi
pass "all authorize paths REFUSED"

bash scripts/ops_live_status.sh --json | "$PY" -c '
import sys, json
d=json.load(sys.stdin)
assert d.get("does_not_authorize") is True
for t in d["tracks"]:
    assert t.get("ready_to_authorize") is False, t
    assert t.get("authorized") is False, t
print("PASS: ops_live_status all ready_to_authorize=false")
'

[[ -f reports/five-products/ops/ENGINEERING_FREEZE.md ]] || fail "missing ENGINEERING_FREEZE.md"
[[ -f reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_V1.md ]] || fail "missing EVAL_V1 unfreeze"
[[ -f reports/five-products/ops/EVAL_V1_E1_INVENTORY.md ]] || fail "missing EVAL_V1 E1 inventory"
grep -q 'prefix="/api/platform/apps/eval"' aiPlat-platform/api/rest/routes.py \
  || fail "eval canonical mount /api/platform/apps/eval missing"
grep -q 'EvalLegacyDeprecationMiddleware' aiPlat-platform/api/rest/routes.py \
  || fail "eval legacy deprecation middleware not wired"
[[ -f aiPlat-core/core/apps/eval/service/store.py ]] || fail "missing EVAL_V1 E2 EvalStore"
[[ -f packages/aiplat-evaluation/contracts/schemas/eval_store.schema.json ]] \
  || fail "missing eval_store.schema.json"
grep -q 'class EvalStore' aiPlat-core/core/apps/eval/service/store.py \
  || fail "EvalStore class missing"
grep -q 'store_api' aiPlat-platform/apps/eval/api/router.py \
  || fail "eval store_api not mounted on eval router"
[[ -f reports/five-products/ops/EVAL_V1_E3_GOLD_SOURCES.md ]] \
  || fail "missing EVAL_V1 E3 gold sources inventory"
[[ -f aiPlat-core/core/apps/eval/service/gold_bootstrap.py ]] \
  || fail "missing EVAL_V1 E3 gold_bootstrap"
grep -q 'bootstrap_e3_gold' aiPlat-core/core/apps/eval/service/gold_bootstrap.py \
  || fail "bootstrap_e3_gold missing"
grep -q 'bootstrap-e3' aiPlat-platform/apps/eval/api/store_api.py \
  || fail "bootstrap-e3 API not wired"
[[ -f aiPlat-core/core/apps/eval/service/judge_v1.py ]] \
  || fail "missing EVAL_V1 E4 judge_v1"
grep -q 'run_e4_calibration' aiPlat-core/core/apps/eval/service/judge_v1.py \
  || fail "run_e4_calibration missing"
grep -q 'calibrate-e4' aiPlat-platform/apps/eval/api/store_api.py \
  || fail "calibrate-e4 API not wired"
[[ -f packages/aiplat-evaluation/contracts/schemas/eval_calibration.schema.json ]] \
  || fail "missing eval_calibration.schema.json"
[[ -f aiPlat-core/core/apps/eval/service/gate_v1.py ]] \
  || fail "missing EVAL_V1 E5 gate_v1"
grep -q 'run_e5_gate' aiPlat-core/core/apps/eval/service/gate_v1.py \
  || fail "run_e5_gate missing"
grep -q 'gate-e5' aiPlat-platform/apps/eval/api/store_api.py \
  || fail "gate-e5 API not wired"
[[ -f packages/aiplat-evaluation/contracts/schemas/eval_gate.schema.json ]] \
  || fail "missing eval_gate.schema.json"
[[ -f aiPlat-core/core/apps/eval/service/g2a.py ]] \
  || fail "missing EVAL_V1 G2a g2a.py"
grep -q 'lock_v0' aiPlat-core/core/apps/eval/service/g2a.py \
  || fail "lock_v0 missing"
grep -q 'gate-g2a' aiPlat-platform/apps/eval/api/store_api.py \
  || fail "gate-g2a API not wired"
grep -q 'lock-v0' aiPlat-platform/apps/eval/api/store_api.py \
  || fail "lock-v0 API not wired"
[[ -f reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md ]] \
  || fail "missing EVAL_V1 UI preview unfreeze"
[[ -f reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_E6.md ]] \
  || fail "missing EVAL_V1 E6 unfreeze"
[[ -f reports/five-products/ops/EVAL_V1_E6_CLOSEOUT.md ]] \
  || fail "missing EVAL_V1 E6 closeout"
[[ -f reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_E7.md ]] \
  || fail "missing EVAL_V1 E7 unfreeze"
[[ -f reports/five-products/ops/EVAL_V1_E7_CLOSEOUT.md ]] \
  || fail "missing EVAL_V1 E7 closeout"
[[ -f reports/five-products/ops/EVALUATION_D2_LOCAL_CLOSEOUT.md ]] \
  || fail "missing evaluation D2 local closeout"
[[ -f aiPlat-management/frontend/src/pages/Eval/EvalCenter.tsx ]] \
  || fail "missing EvalCenter (E6)"
grep -q "EvalCenter" aiPlat-management/frontend/src/App.tsx \
  || fail "App.tsx must mount EvalCenter"
[[ -f reports/five-products/ops/ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md ]] \
  || fail "missing DIAGNOSIS_V1 C0 unfreeze"
[[ -f docs/architecture/plans/diagnosis-v1-charter.md ]] \
  || fail "missing diagnosis-v1-charter"
[[ -f reports/five-products/ops/DIAGNOSIS_V1_C0_SEED_CASES.md ]] \
  || fail "missing DIAGNOSIS_V1 C0 seed cases"
[[ -f reports/five-products/modules/diagnosis/contracts/schemas/diagnosis_evidence.schema.json ]] \
  || fail "missing diagnosis evidence schema v0"
[[ -f reports/five-products/ops/ENGINEERING_UNFREEZE_DIAGNOSIS_C3.md ]] \
  || fail "missing DIAGNOSIS_V1 C3 unfreeze"
[[ -f reports/five-products/ops/DIAGNOSIS_V1_C3_CLOSEOUT.md ]] \
  || fail "missing DIAGNOSIS_V1 C3 closeout"
[[ -x packages/aiplat-diagnosis/scripts/d2_local_closeout.sh ]] \
  || fail "missing diagnosis d2_local_closeout"
[[ -f packages/aiplat-diagnosis/security/baseline.yaml ]] \
  || fail "missing diagnosis security baseline"
[[ -f aiPlat-management/frontend/src/pages/Eval/EvalPreview.tsx ]] \
  || fail "missing /eval preview page"
grep -q "path: 'eval'" aiPlat-management/frontend/src/App.tsx \
  || fail "/eval route missing in App.tsx"
grep -q "key: '/eval'" aiPlat-management/frontend/src/pageManifest.ts \
  || fail "/eval menu entry missing in pageManifest"
[[ -f reports/five-products/ops/STAGING_REVIEW_2026-11-08.md ]] || fail "missing STAGING_REVIEW 2026-11-08"
[[ -f reports/five-products/ops/STAGING_REVIEW_2026-11-15.md ]] || fail "missing STAGING_REVIEW 2026-11-15"
[[ -f reports/five-products/ops/STAGING_REVIEW_2026-11-22.md ]] || fail "missing STAGING_REVIEW 2026-11-22"
[[ -f reports/five-products/ops/STAGING_REVIEW_EVENT_DRIVEN.md ]] || fail "missing STAGING_REVIEW_EVENT_DRIVEN"
grep -q '事件驱动' reports/five-products/ops/STAGING_REVIEW_EVENT_DRIVEN.md \
  || fail "STAGING_REVIEW_EVENT_DRIVEN must declare event-driven policy"
grep -q 'cancelled_calendar_review' reports/five-products/ops/STAGING_REVIEW_2026-11-29.md \
  || fail "STAGING_REVIEW_2026-11-29 must stay cancelled (no calendar churn)"
grep -q 'staging_ready=false' reports/five-products/ops/STAGING_READY.md \
  || fail "STAGING_READY must remain false until review"
grep -q 'continue_defer' reports/five-products/ops/STAGING_REVIEW_2026-11-15.md \
  || fail "STAGING_REVIEW_2026-11-15 must record continue_defer"
grep -q 'continue_defer' reports/five-products/ops/STAGING_REVIEW_2026-11-22.md \
  || fail "STAGING_REVIEW_2026-11-22 must record continue_defer"

pass "engineering freeze check"
echo "NOTE: staging review is event-driven (host/DSN/OIDC) — Option B local; no calendar churn."
