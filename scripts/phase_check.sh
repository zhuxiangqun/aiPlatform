#!/usr/bin/env bash
# ============================================================================
# phase_check.sh — Phase 验收检查清单
#
# 每个 Phase 完成后必须运行此脚本。三步全部 PASS 才算 Phase 完成。
#
# Usage: bash scripts/phase_check.sh
#
# Integrated into architecture_guard.sh as the final step.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILURES=0

_log() { echo -e "$@" >&2; }

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  PHASE CHECK — 五步验收清单"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ══════════════════════════════════════════════════════════════
# Step 1: Dead code detection (caller_verify.sh)
# ══════════════════════════════════════════════════════════════
echo "━━━ Step 1/5: Dead Code Detection ━━━"
echo ""
if bash "$SCRIPT_DIR/caller_verify.sh"; then
    echo -e "${GREEN}  PASS${NC} Step 1: No 0-caller symbols detected"
else
    echo -e "${RED}  FAIL${NC} Step 1: 0-caller symbols found (see above)"
    FAILURES=$((FAILURES + 1))
fi

# ══════════════════════════════════════════════════════════════
# Step 2: Wiring assertion tests
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 2/5: Wiring Assertion Tests ━━━"
echo ""
if python3 -m pytest "$WORKSPACE/aiPlat-core/core/tests/wiring/test_wiring.py" "$WORKSPACE/aiPlat-core/core/tests/wiring/test_methods_wired.py" -v --tb=short -q 2>&1; then
    echo -e "${GREEN}  PASS${NC} Step 2: All wiring tests passed"
else
    echo -e "${RED}  FAIL${NC} Step 2: Wiring test failures (see above)"
    FAILURES=$((FAILURES + 1))
fi

# ══════════════════════════════════════════════════════════════
# Step 2.5: Method-level caller verification
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 2.5/5: Method-Level Caller Verification ━━━"
echo ""
if bash "$SCRIPT_DIR/method_verify.sh"; then
    echo -e "${GREEN}  PASS${NC} Step 2.5: All key methods have callers"
else
    echo -e "${YELLOW}  WARN${NC} Step 2.5: Some methods lack callers (see above — may be internal helpers)"
fi

# ══════════════════════════════════════════════════════════════
# Step 3: Wiring integration tests
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 3/5: Wiring Integration Tests ━━━"
echo ""
if python3 -m pytest "$WORKSPACE/aiPlat-core/core/tests/wiring/integration/" -v --tb=short -q 2>&1; then
    echo -e "${GREEN}  PASS${NC} Step 3: All integration tests passed"
else
    echo -e "${RED}  FAIL${NC} Step 3: Integration test failures (see above)"
    FAILURES=$((FAILURES + 1))
fi

# ══════════════════════════════════════════════════════════════
# Step 4: Self-annotated dead code scan
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 4/5: Self-Annotated Dead Code Scan ━━━"
echo ""
DEAD_MARKERS=$(grep -rn "TODO.*wire\|0 caller\|待接线\|FIXME.*wire\|# DEAD" \
    "$WORKSPACE/aiPlat-core/core/" \
    --include='*.py' 2>/dev/null \
    | grep -v __pycache__ \
    | grep -v '.pyc' || true)

if [ -z "$DEAD_MARKERS" ]; then
    echo -e "${GREEN}  PASS${NC} Step 4: No self-annotated dead code found"
else
    echo -e "${YELLOW}  WARN${NC} Step 4: Self-annotated dead code markers found:"
    echo "$DEAD_MARKERS" | head -20
    count=$(echo "$DEAD_MARKERS" | wc -l | tr -d ' ')
    echo "  Total: $count instances"
    echo -e "${YELLOW}  WARN${NC} Step 4: Review markers above. Remove if no longer applicable."
fi

# ══════════════════════════════════════════════════════════════
# Step 5: Compile verification (sanity)
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 5/5: Compile Verification ━━━"
echo ""
COMPILE_ERRORS=0
for f in $(find "$WORKSPACE/aiPlat-core/core/harness" "$WORKSPACE/aiPlat-core/core/apps" "$WORKSPACE/aiPlat-core/core/api" "$WORKSPACE/aiPlat-core/core/services" "$WORKSPACE/aiPlat-core/core/gateway" -name "*.py" -not -path "*/tests/*" -not -path "*/__pycache__/*" 2>/dev/null | sort -R | head -50); do
    if ! python3 -m py_compile "$f" 2>/dev/null; then
        COMPILE_ERRORS=$((COMPILE_ERRORS + 1))
    fi
done
if [ "$COMPILE_ERRORS" -eq 0 ]; then
    echo -e "${GREEN}  PASS${NC} Step 5: Random 50 files compile OK"
else
    echo -e "${RED}  FAIL${NC} Step 5: $COMPILE_ERRORS file(s) failed to compile"
    FAILURES=$((FAILURES + 1))
fi

# ══════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}═══ PHASE CHECK PASSED — all 5 steps clear ═══${NC}"
    exit 0
else
    echo -e "${RED}═══ PHASE CHECK FAILED: $FAILURES step(s) failed ═══${NC}"
    echo ""
    echo "  Fix required before Phase completion:"
    echo "    - Step 1 failed: run 'bash scripts/caller_verify.sh' to see dead symbols"
    echo "    - Step 2 failed: run 'pytest tests/wiring/test_wiring.py test_methods_wired.py -v'"
    echo "    - Step 3 failed: run 'pytest tests/wiring/integration/ -v'"
    echo "    - Step 5 failed: run 'python -m py_compile' on the failing file"
    exit 1
fi
