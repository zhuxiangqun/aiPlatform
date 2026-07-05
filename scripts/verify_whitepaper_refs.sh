#!/usr/bin/env bash
# verify_whitepaper_refs.sh — validate code references in aiPlat whitepaper
# Usage: bash scripts/verify_whitepaper_refs.sh [whitepaper_path]
# Exit 0 if all references resolve; exit 1 with WARNING on stale refs

set -euo pipefail

WP="${1:-docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md}"
if [ ! -f "$WP" ]; then
    echo "ERROR: whitepaper not found: $WP"
    exit 1
fi

STALE=0
WARN=0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

check_ref() {
    local label="$1"
    local raw_path="$2"
    local expected_min="${3:-1}"
    local expected_exact="${4:-}"
    local path
    # Expand ~ and handle absolute vs relative paths
    if [[ "$raw_path" == /* ]]; then
        path="$raw_path"
    elif [[ "$raw_path" == ~* ]]; then
        path="${raw_path/#\~/$HOME}"
    else
        path="${ROOT}/${raw_path}"
    fi
    local found

    if [ ! -f "$path" ]; then
        echo "  ⚠️  STALE: $label — file missing: $path"
        STALE=$((STALE + 1))
        return
    fi

    if [ -n "$expected_exact" ]; then
        found=$(grep -c "$expected_exact" "$path" 2>/dev/null || true)
        found=${found:-0}
        if [ "$found" -eq 0 ]; then
            echo "  ⚠️  STALE: $label — exact match not found: $expected_exact in $path"
            STALE=$((STALE + 1))
            return
        fi
    fi

    found=$(wc -l < "$path" 2>/dev/null || true)
    found=${found:-0}
    if [ "$found" -lt "$expected_min" ]; then
        echo "  ⚠️  WARN: $label — file smaller than expected: $found lines (min $expected_min) in $path"
        WARN=$((WARN + 1))
        return
    fi

    echo "  ✅ $label"
}

echo "=== Verifying whitepaper code references ==="
echo "Date: $(date -u +%Y-%m-%d)"
echo "Target: $WP"
echo ""

# ── Phase-by-phase evidence checks ──

echo "[A. Autonomy]"
check_ref "_retry_loop" "aiPlat-core/core/harness/execution/pipeline_engine.py" 100 "async def _retry_loop"
check_ref "_meta_optimize" "aiPlat-core/core/harness/execution/pipeline_engine.py" 100 "async def _meta_optimize"
check_ref "HITL config" "aiPlat-core/core/apps/agents/operator_agent.py" 50 "AIPLAT_OPERATOR_CONFIRMATION_LEVEL"
echo ""

echo "[B. Context Awareness]"
check_ref "RunContext" "aiPlat-core/core/harness/kernel/types.py" 50 "class RunContext"
check_ref "CRAG" "aiPlat-core/core/apps/agents/materials_chat.py" 200 "CRAG"
check_ref "DomainRouter" "aiPlat-core/core/harness/knowledge/domain_router.py" 100 "class DomainRouter"
check_ref "OntologyEngine" "aiPlat-core/core/harness/ontology_engine/engine.py" 300
echo ""

echo "[C. Tool Mastery]"
check_ref "PolicyGate" "aiPlat-core/core/harness/infrastructure/gates/policy_gate.py" 800 "class PolicyGate"
check_ref "ApprovalGate" "aiPlat-core/core/harness/infrastructure/gates/approval_gate.py" 200 "class ApprovalGate"
check_ref "SandboxGate" "aiPlat-core/core/harness/infrastructure/gates/sandbox_gate.py" 50 "Sandbox"
echo ""

echo "[D. Memory]"
check_ref "MemoryManager" "aiPlat-core/core/harness/memory/manager.py" 200 "build_context"
check_ref "Semantic conflict" "aiPlat-core/core/harness/memory/semantic.py" 100 "_resolve_semantic_conflict"
check_ref "Episodic TTL" "aiPlat-core/core/harness/memory/episodic.py" 100 "cleanup_expired"
check_ref "MemoryOS Agent" "${HOME}/.aiplat/agents/memory_os/AGENT.md" 10
echo ""

echo "[E. Coordination]"
check_ref "integration.py" "aiPlat-core/core/harness/integration.py" 1000
echo ""

echo "[F. Self-Evolution]"
check_ref "FailoverReason" "aiPlat-core/core/harness/infrastructure/gates/error_translator.py" 100 "class FailoverReason"
check_ref "Healing strategies" "aiPlat-core/core/harness/execution/pipeline_engine.py" 100 "async def _strategy_rotate_credential"
check_ref "PromptOptimizer" "aiPlat-core/core/harness/optimization/prompt_optimizer.py" 50 "class PromptOptimizer"
check_ref "CredentialPool" "aiPlat-infra/infra/management/model/credential_pool.py" 100 "class CredentialPool"
# Phase 25-28
check_ref "ExecutionSnapshot" "aiPlat-core/core/harness/execution/snapshot.py" 100 "class ExecutionSnapshot"
check_ref "StrategyTracker" "aiPlat-core/core/harness/optimization/strategy_tracker.py" 100 "class StrategyEffectivenessTracker"
check_ref "SharedKnowledgePool" "aiPlat-core/core/harness/memory/shared_pool.py" 100 "class SharedKnowledgePool"
check_ref "GoalGenerator" "aiPlat-core/core/harness/optimization/goal_generator.py" 100 "class GoalGenerator"
echo ""

# ── Summary ──
echo "=============================="
if [ "$STALE" -gt 0 ]; then
    echo "ERROR: $STALE stale reference(s) — whitepaper is out of sync with code"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    echo "WARNING: $WARN reference(s) need review (file smaller than expected)"
    exit 0
else
    echo "✅ All whitepaper code references verified"
    exit 0
fi
