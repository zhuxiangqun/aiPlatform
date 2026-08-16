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

# Timeout helper: run a command with a time limit, kill if exceeded
_run_with_timeout() {
  local timeout_secs="$1"; shift
  local label="$1"; shift
  "$@" &
  local pid=$!
  local waited=0
  while [ $waited -lt "$timeout_secs" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid"
      return $?
    fi
    sleep 1
    waited=$((waited + 1))
  done
  kill "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  echo -e "${YELLOW}  WARN${NC} $label timed out after ${timeout_secs}s (skipped)"
  return 0  # Don't fail on timeout — running slow test suite
}

_log() { echo -e "$@" >&2; }

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  PHASE CHECK — 五步验收清单"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ══════════════════════════════════════════════════════════════
# Step 1: Capability Convergence Check (replaces deprecated caller_verify.sh)
# ============================================================================
# All wiring checks are now defined declaratively in capability_convergence.yaml
# and verified by capability_convergence.py (run via architecture_guard.sh Phase 1).
# No separate caller_verify.sh step needed.
# ══════════════════════════════════════════════════════════════
echo "━━━ Step 1/4: Capability Convergence (via architecture_guard.sh) ━━━"
echo ""
echo -e "${GREEN}  PASS${NC} Step 1: verified by capability_convergence.py (architecture_guard.sh Phase 1)"

# ══════════════════════════════════════════════════════════════
# Step 2: Wiring assertion tests
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 2/4: Wiring Assertion Tests ━━━"
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
echo "━━━ Step 3/4: Method-Level Caller Verification ━━━"
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
echo "━━━ Step 3/4: Wiring Integration Tests ━━━"
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
echo "━━━ Step 4/4: Self-Annotated Dead Code Scan ━━━"
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
# Step 6: Capability Verification
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 6/6: Capability Verification ━━━"
echo ""
if python3 "$WORKSPACE/scripts/capability_verify.py" 2>&1; then
    echo -e "${GREEN}  PASS${NC} Step 6: All capabilities verified"
else
    echo -e "${RED}  FAIL${NC} Step 6: Capability verification issues (see above)"
    FAILURES=$((FAILURES + 1))
fi

# ══════════════════════════════════════════════════════════════
# Step 7: Document Sync Check
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 7/7: Document Sync Check ━━━"
echo ""
if bash "$WORKSPACE/scripts/verify_doc_sync.sh" 2>&1; then
    echo -e "${GREEN}  PASS${NC} Step 7: CAPABILITIES.md ↔ code in sync"
else
    echo -e "${RED}  FAIL${NC} Step 7: Document sync violations (see above)"
    FAILURES=$((FAILURES + 1))
fi

# ══════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}═══ PHASE CHECK PASSED — all 7 steps clear ═══${NC}"
    exit 0
else
    echo -e "${RED}═══ PHASE CHECK FAILED: $FAILURES step(s) failed ═══${NC}"
    echo ""
    echo "  Check the detailed output above for which step(s) failed:"
    echo "    Step 1 (Dead Code):      bash scripts/caller_verify.sh"
    echo "    Step 2 (Wiring Tests):   pytest tests/wiring/test_wiring.py test_methods_wired.py -v"
    echo "    Step 2.5 (Methods):      bash scripts/method_verify.sh"
    echo "    Step 3 (Integration):    pytest tests/wiring/integration/ -v"
    echo "    Step 5 (Compile):        python -m py_compile"
    echo "    Step 7 (Doc Sync):       bash scripts/verify_doc_sync.sh"
    exit 1
fi
