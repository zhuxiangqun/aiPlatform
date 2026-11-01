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
