#!/usr/bin/env bash
# Pi D3 N-1 local rehearsal — install → upgrade → runtime rollback → smoke.
# Marks checklist #6 as 🟨 only. Never sets d3_production_authorized=true.
# Not a staging/live drill (see LIVE_DRILL_EVIDENCE.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DRILL_DIR="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_PI_D3_N1_DEMO_ROOT:-/tmp/aiplat-pi-d3-n1-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_PI_PREFIX="$DEMO_ROOT/pi"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_PI_PREFIX"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== Pi D3 N-1 local rehearsal (environment=local) =="
echo "DEMO_ROOT=$DEMO_ROOT PREFIX=$AIPLAT_PI_PREFIX"

bash "$SCRIPT_DIR/d1_install.sh" --smoke || fail "d1_install --smoke"
BEFORE="$(readlink "$AIPLAT_PI_PREFIX/current" 2>/dev/null || true)"
[[ -n "$BEFORE" ]] || fail "missing current after install"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "d1_upgrade"
AFTER="$(readlink "$AIPLAT_PI_PREFIX/current" 2>/dev/null || true)"
[[ -n "$AFTER" && "$AFTER" != "$BEFORE" ]] || fail "upgrade did not flip current ($BEFORE → $AFTER)"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "d1_rollback --runtime"
ROLLED="$(readlink "$AIPLAT_PI_PREFIX/current" 2>/dev/null || true)"
[[ "$ROLLED" == "$BEFORE" ]] || fail "rollback did not restore $BEFORE (got $ROLLED)"
bash "$SCRIPT_DIR/d1_smoke.sh" || fail "smoke after rollback"

OUT="$DRILL_DIR/n1-rehearsal-${STAMP}.json"
python3 - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(
    json.dumps(
        {
            "kind": "pi_d3_n1_local_rehearsal_not_production",
            "at": "$STAMP",
            "environment": "local",
            "demo_root": "$DEMO_ROOT",
            "before_current": "$BEFORE",
            "after_upgrade": "$AFTER",
            "after_rollback": "$ROLLED",
            "smoke_after_rollback": True,
            "d3_production": False,
            "production_signed": False,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("OK wrote", r"""$OUT""")
PY

CL="$ROOT/packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md"
python3 - <<PY
from pathlib import Path
p = Path(r"""$CL""")
t = p.read_text(encoding="utf-8")
t = t.replace(
    "| 6 | N-1 升级/回滚 live 或等价演练 | 运维 | ⬜ |",
    "| 6 | N-1 升级/回滚 live 或等价演练 | 运维 | 🟨 |",
)
assert "d3_production_authorized: false" in t
p.write_text(t, encoding="utf-8")
print("OK checklist #6 → 🟨 (d3_production still false)")
PY

pass "pi d3_n1_local_rehearsal stamp=$STAMP d3_production_authorized=false"
