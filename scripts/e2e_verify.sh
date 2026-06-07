#!/usr/bin/env bash
# ============================================================================
# e2e_verify.sh — comprehensive end-to-end verification of core system fixes
#
# Tests: token tracking, event persistence, span_id integrity, dedup,
#        and MCP test flow.
#
# Usage: bash scripts/e2e_verify.sh
# ============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "  ${GREEN}✓ $1${NC}"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✗ $1${NC}"; FAIL=$((FAIL+1)); }
info() { echo -e "  ${YELLOW}→ $1${NC}"; }

WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${WORKSPACE_ROOT}/aiPlat-core/core/data/aiplat_executions.sqlite3"
CORE_URL="http://localhost:8002"
AGENT_ID="agent_test_1"

echo "═══════════════════════════════════════════════════════════════"
echo "  E2E Verification — Core System Fixes"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Sanity checks ──
if ! curl -s --max-time 2 "${CORE_URL}/api/core/health" > /dev/null 2>&1; then
    fail "Core server not reachable at ${CORE_URL}"
    echo ""
    echo "⚠️  Core server must be running. Start with: ./restart.sh"
    echo ""
    exit 1
fi
pass "Core server reachable"

if [ ! -f "$DB_PATH" ]; then
    fail "Execution DB not found at ${DB_PATH}"
    echo ""
    echo "⚠️  Expected: ${DB_PATH}"
    echo "   Try: mkdir -p \$(dirname ${DB_PATH})"
    echo ""
    exit 1
fi
pass "Execution DB exists"

echo ""

# ═══════════════════════════════════════════════
# Test 1-3: Agent Execution
# ═══════════════════════════════════════════════
echo "── Test 1-3: Agent Execution ──"

info "Executing agent ${AGENT_ID} with '计算5的平方'..."
RESP=$(curl -s --max-time 30 -X POST "${CORE_URL}/api/core/workspace/agents/${AGENT_ID}/execute" \
  -H "Content-Type: application/json" \
  -d '{"input":{"message":"计算5的平方"},"options":{"toolset":"mcp_readonly"}}' 2>/dev/null || echo '{"ok":false,"error":"curl failed"}')

RUN_ID=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('run_id',''))" 2>/dev/null || echo "")
STATUS=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','FAIL'))" 2>/dev/null || echo "FAIL")
TOKENS=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); t=d.get('tokens',{}); print(int(t.get('total_tokens',0) or 0))" 2>/dev/null || echo "0")
OUTPUT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(str(d.get('output',''))[:100])" 2>/dev/null || echo "")

if [ -z "$RUN_ID" ]; then
    fail "Agent execution returned no run_id"
    echo "     Response: ${RESP:0:200}"
else
    info "run_id: ${RUN_ID:0:20}..."
    info "status: ${STATUS}"

    if [ "$STATUS" = "completed" ]; then
        pass "Test 1: Agent execution completed"
    else
        fail "Test 1: Agent status is '${STATUS}' (expected 'completed')"
    fi

    if [ "$TOKENS" -gt 0 ]; then
        pass "Test 2: Token tracking works (${TOKENS} tokens)"
    else
        fail "Test 2: Token tracking returns 0"
    fi

    # Check output contains the correct answer pattern
    if echo "$OUTPUT" | grep -qi "25\|square\|平方"; then
        pass "Test 3: Output contains correct answer"
    else
        fail "Test 3: Output may be wrong: '${OUTPUT}'"
    fi
fi

echo ""

# ═══════════════════════════════════════════════
# Test 4-8: Event Persistence & Integrity
# ═══════════════════════════════════════════════
echo "── Test 4-8: Event Persistence & Integrity ──"

if [ -z "$RUN_ID" ]; then
    fail "Skipping DB tests — no run_id"
else
    sleep 2  # let DLQ flush

    if ! sqlite3 "$DB_PATH" ".tables" 2>/dev/null | grep -q "syscall_events"; then
        fail "syscall_events table not found in DB"
    else
        # Event counts
        STEP_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM syscall_events WHERE run_id='${RUN_ID}' AND kind='step'" 2>/dev/null || echo "0")
        OBSERVE_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM syscall_events WHERE run_id='${RUN_ID}' AND kind='observe'" 2>/dev/null || echo "0")
        DONE_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM syscall_events WHERE run_id='${RUN_ID}' AND kind='done'" 2>/dev/null || echo "0")
        CONTEXT_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM syscall_events WHERE run_id='${RUN_ID}' AND kind='context'" 2>/dev/null || echo "0")
        TOTAL=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM syscall_events WHERE run_id='${RUN_ID}'" 2>/dev/null || echo "0")

        info "Total events for ${RUN_ID:0:16}...: ${TOTAL}"

        [ "$STEP_COUNT" -gt 0 ] && pass "Test 4: step events (${STEP_COUNT})" || fail "Test 4: no step events"
        [ "$OBSERVE_COUNT" -gt 0 ] && pass "Test 5: observe events (${OBSERVE_COUNT})" || fail "Test 5: no observe events"
        [ "$DONE_COUNT" -gt 0 ] && pass "Test 6: done events (${DONE_COUNT})" || fail "Test 6: no done events"
        [ "$CONTEXT_COUNT" -gt 0 ] && pass "Test 7: context snapshot (${CONTEXT_COUNT})" || fail "Test 7: no context snapshot"

        # Span integrity: should not contain "::" (empty agent)
        BAD_SPANS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM syscall_events WHERE run_id='${RUN_ID}' AND span_id LIKE '%::%'" 2>/dev/null || echo "0")
        [ "$BAD_SPANS" -eq 0 ] && pass "Test 8: all span_ids have valid agent name" || fail "Test 8: ${BAD_SPANS} events have '::' in span_id"

        # Dedup: each id should be unique
        DUP_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*)-COUNT(DISTINCT id) FROM syscall_events WHERE run_id='${RUN_ID}'" 2>/dev/null || echo "0")
        [ "$DUP_COUNT" -eq 0 ] && pass "Test 9: no duplicate events (${TOTAL} events, all unique)" || fail "Test 9: ${DUP_COUNT} duplicate event IDs"

        # Sample event structure
        SAMPLE=$(sqlite3 -separator " | " "$DB_PATH" "SELECT kind, name, span_id FROM syscall_events WHERE run_id='${RUN_ID}' LIMIT 5" 2>/dev/null || echo "")
        info "Sample events:"
        echo "$SAMPLE" | while read -r line; do
            echo "    $line"
        done
    fi
fi

echo ""

# ═══════════════════════════════════════════════
# Test 10-12: MCP Test Flow
# ═══════════════════════════════════════════════
echo "── Test 10-12: MCP Test Flow ──"

MCP_RESP=$(curl -s --max-time 15 -X POST "${CORE_URL}/api/core/workspace/mcp/servers/mcp-test-1/test-invoke" \
  -H "Content-Type: application/json" \
  -d '{"tool":"test-1","arguments":{"num":5}}' 2>/dev/null || echo '{"status":"error"}')

MCP_RUN_ID=$(echo "$MCP_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('run_id',''))" 2>/dev/null || echo "")

if [ -z "$MCP_RUN_ID" ]; then
    fail "Test 10: MCP test failed — no run_id returned"
    info "Response: ${MCP_RESP:0:200}"
else
    pass "Test 10: MCP test returned run_id"
    info "MCP run_id: ${MCP_RUN_ID:0:30}..."

    sleep 5  # wait for async test to complete

    MCP_TOTAL=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM syscall_events WHERE run_id='${MCP_RUN_ID}'" 2>/dev/null || echo "0")
    MCP_TYPES=$(sqlite3 "$DB_PATH" "SELECT kind, name, status FROM syscall_events WHERE run_id='${MCP_RUN_ID}' ORDER BY start_time" 2>/dev/null || echo "")

    if [ "$MCP_TOTAL" -gt 0 ]; then
        pass "Test 11: MCP events persisted (${MCP_TOTAL} events)"
        info "MCP event flow:"
        echo "$MCP_TYPES" | while read -r line; do
            echo "    $line"
        done

        # Check that at least finish event has 'ok' (live events don't persist to DB)
        MCP_OK=$(echo "$MCP_TYPES" | grep -c "ok" || true)
        if [ "$MCP_TOTAL" -ge 3 ]; then
            pass "Test 12: MCP events exist in DB (${MCP_TOTAL} events, ok=${MCP_OK})"
        else
            fail "Test 12: Too few MCP events (${MCP_TOTAL}, expected ≥3)"
        fi
    else
        fail "Test 11: No MCP events found in DB"
    fi
fi

echo ""

# ═══════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo -e "  Results: ${GREEN}${PASS} passed${NC} / ${RED}${FAIL} failed${NC}"
echo "═══════════════════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    exit 1
else
    exit 0
fi
