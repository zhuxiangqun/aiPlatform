#!/bin/bash
# check-genericity.sh — Developer self-check for Core/Infra genericity
# Run before committing changes to core/ or infra/ layers.
# Covers: engine agnostic + core genericity + architecture guard §77-88.

set -e

WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

sep() { echo "════════════════════════════════════════════════════════════"; }
check() { printf "  %-50s %s\n" "$1" "$2"; }
gc() { grep -c "$1" "$2" 2>/dev/null || echo 0; }

echo ""
sep; echo "  GENERICITY SELF-CHECK"; sep; echo ""

# ── 1. Engine layer compliance ──
echo "  [1/4] Engine layer compliance"
if bash "$WORKSPACE/scripts/pre-commit-engine-guard.sh" 2>&1 | tail -3; then
    check "Engine layer" "✅"
else
    check "Engine layer" "❌"; FAIL=1
fi

# ── 2. Core genericity tests ──
echo ""; echo "  [2/4] Core genericity tests (8 checks)"
if python3 -m pytest "$WORKSPACE/aiPlat-core/core/tests/constitution/test_core_genericity.py" -q --tb=short 2>&1 | tail -5; then
    check "Core genericity" "✅"
else
    check "Core genericity" "❌"; FAIL=1
fi

# ── 3. Engine agnostic tests ──
echo ""; echo "  [3/4] Engine agnostic tests (4 checks)"
if python3 -m pytest "$WORKSPACE/aiPlat-core/core/tests/constitution/test_engine_agnostic.py" -q --tb=short 2>&1 | tail -5; then
    check "Engine agnostic" "✅"
else
    check "Engine agnostic" "❌"; FAIL=1
fi

# ── 4. Architecture guard §77-88 (grep-level) ──
echo ""; echo "  [4/4] Architecture guard §77-88"
VIOLATIONS=0

_run_check() {
    local rule="$1" label="$2" count="$3"
    if [ "${count:-0}" -gt 0 ] 2>/dev/null; then
        check "$label" "❌ ($count)"; VIOLATIONS=$((VIOLATIONS + 1))
    else
        check "$label" "✅"
    fi
}

cd "$WORKSPACE"

# Engine layer (§77-79)
c77=$(grep -rn '"architecture".*"code".*"test_report"\|state\.get("architecture"\|state\.get("code"\|state\.get("test_report"' aiPlat-core/core/harness/execution/ --include='*.py' 2>/dev/null | grep -v '_run_stage_skill\|#\|test_\|snapshot' | wc -l | tr -d ' ')
_run_check 77 "§77: engine artifact keys" "$c77"

c78=$(grep -rn '你是\|你是一个\|请将\|请基于' aiPlat-core/core/harness/execution/ --include='*.py' 2>/dev/null | grep -v '#\|prompt_loader\|test_\|_sync_resolve' | wc -l | tr -d ' ')
_run_check 78 "§78: engine Chinese prompts" "$c78"

c79=$(grep -c '"architecture_design"\|"code_generation"\|"test_case_generation"' aiPlat-core/core/harness/execution/pipeline_engine.py 2>/dev/null || echo 0)
_run_check 79 "§79: pipeline skill names" "$c79"

# Core genericity (§80-88)
c80=$(grep -rn '"fde-delivery"\|"lock-service"\|"bell-consulting"\|"bell-data-cloud"\|"bell-healthcare"\|"bell-global"\|"enterprise-terms"' aiPlat-core/core/harness/ --include='*.py' 2>/dev/null | grep -v '#\|test_\|builtin_handlers\|builtin_actions\|domain_router\|ontology_loader\|_scan_domain\|_DOMAIN_PROMPT_DEFAULTS\|prompt_loader.py\|ontology_branch.py\|ontology_validator.py' | wc -l | tr -d ' ')
_run_check 80 "§80: hardcoded domain IDs" "$c80"

c81=$(grep -c '"DiagnosisSession"\|"DeliveryAction"\|"Term"' aiPlat-core/core/api/routers/system.py 2>/dev/null || echo 0)
_run_check 81 "§81: domain class names" "$c81"

c82=$(grep -c 'domain_id="fde-delivery"\|domain_id="lock-service"\|domain_id="bell-' aiPlat-core/core/harness/ontology_engine/builtin_actions.py 2>/dev/null || echo 0)
_run_check 82 "§82: builtin business actions" "$c82"

c83=$(grep -c '审核路径\|七步周天\|认知同化' aiPlat-core/core/harness/knowledge/conversation_ingestor.py 2>/dev/null || echo 0)
_run_check 83 "§83: ingestion keywords" "$c83"

c84=$(grep -c '"lock-service".*"fde-delivery"\|"客户现场".*"客户"' aiPlat-core/core/harness/knowledge_pipeline/resolver.py 2>/dev/null || echo 0)
_run_check 84 "§84: cross-domain seed" "$c84"

c85=$(grep -c 'architect_agent\|programmer_agent\|qa_agent' aiPlat-core/core/harness/execution/team_planner.py 2>/dev/null || echo 0)
_run_check 85 "§85: default team stages" "$c85"

c86=$(grep -c '_register("domain-prompt-' aiPlat-core/core/harness/utils/prompt_loader.py 2>/dev/null || echo 0)
_run_check 86 "§86: domain prompt registrations" "$c86"

c87=$(grep -c '_register("agent-pm_agent"\|_register("agent-architect_agent"\|_register("agent-programmer_agent"' aiPlat-core/core/harness/utils/prompt_loader.py 2>/dev/null || echo 0)
_run_check 87 "§87: agent SOP registrations" "$c87"

c88=$(grep -c 'GraphIndex.load("' aiPlat-core/core/harness/ontology_engine/builtin_handlers.py 2>/dev/null || echo 0)
_run_check 88 "§88: hardcoded handler domains" "$c88"

if [ "$VIOLATIONS" -gt 0 ]; then
    FAIL=1
fi

# ── Aggregate ──
echo ""
sep
if [ "$FAIL" -ne 0 ]; then
    echo "  ❌ GENERICITY CHECK FAILED — fix violations before committing"
    sep; exit 1
else
    echo "  ✅ ALL GENERICITY CHECKS PASSED (engine agnostic + core genericity + guard)"
    sep; exit 0
fi
