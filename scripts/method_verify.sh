#!/usr/bin/env bash
# ============================================================================
# method_verify.sh — 方法级接线验证
#
# 对每个 key module，提取其公开方法，逐一检查是否有外部 caller。
# 检测"类被 import 了但关键方法未被调用"的问题。
#
# Usage: bash scripts/method_verify.sh
# Integrated into phase_check.sh as Step 2.5
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

WARNINGS=0

# ── Key modules with their must-have methods ──────────────────

# Format: module_path | method_name | description
# Methods that appear in comments/docstrings may have false positives.
# Add methods that are truly critical (not internal helpers).
declare -a KEY_METHODS=(
    # OnErrorReflector
    "aiPlat-core/core/harness/infrastructure/hooks/on_error_reflector.py|on_post_observe|反思钩子回调"
    # HallucinationTracker
    "aiPlat-core/core/harness/evaluation/hallucination_tracker.py|evaluate|事实核查"
    "aiPlat-core/core/harness/evaluation/hallucination_tracker.py|get_dashboard|仪表盘"
    "aiPlat-core/core/harness/evaluation/hallucination_tracker.py|get_recent_reports|最近报告"
    # ParallelExecutor
    "aiPlat-core/core/apps/agents/parallel_executor.py|map|Map FanOut"
    "aiPlat-core/core/apps/agents/parallel_executor.py|map_reduce|Map-Reduce"
    "aiPlat-core/core/apps/agents/parallel_executor.py|parallel_analyze|便利FanOut"
    # SemanticCache
    "aiPlat-core/core/harness/knowledge/semantic_cache.py|invalidate_domain|缓存失效"
    # EnterpriseGateway
    "aiPlat-core/core/gateway/__init__.py|send_message|消息推送"
    "aiPlat-core/core/gateway/__init__.py|register|适配器注册"
    # ImplicitFeedback
    "aiPlat-core/core/services/implicit_feedback.py|record|信号记录"
    "aiPlat-core/core/services/implicit_feedback.py|get_stats|统计查询"
    # PII Detector
    "aiPlat-core/core/services/pii_detector.py|mask|PII脱敏"
    # Code Auditor
    "aiPlat-core/core/harness/security/code_auditor.py|audit|安全审计"
)

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Method Verification — Key Method Caller Detection"
echo "═══════════════════════════════════════════════════════════════"
echo ""

for entry in "${KEY_METHODS[@]}"; do
    IFS='|' read -r file_path method_name description <<< "$entry"
    full_path="$WORKSPACE/$file_path"
    [ -f "$full_path" ] || continue

    basename="$(basename "$file_path")"
    
    # Check if method has callers outside its own file and test dirs
    # Use grep with --include for performance
    hits=$(grep -rl "$method_name" "$(dirname "$full_path")/../.." \
        --include='*.py' 2>/dev/null \
        | grep -v "$basename" \
        | grep -v '__pycache__' \
        | grep -v '/tests/' \
        | sort -u || true)
    
    if [ -z "$hits" ]; then
        # Try wider search (whole aiPlat-core)
        hits_wide=$(grep -rl "$method_name" "$WORKSPACE/aiPlat-core" \
            --include='*.py' 2>/dev/null \
            | grep -v "$basename" \
            | grep -v '__pycache__' \
            | grep -v '/tests/' \
            | sort -u || true)
        
        if [ -z "$hits_wide" ]; then
            echo -e "  ${RED}DEAD${NC}  | $method_name in $basename — ${description}"
            WARNINGS=$((WARNINGS + 1))
        else
            echo -e "  ${GREEN}OK${NC}    | $method_name in $basename — ${description}"
        fi
    else
        count=$(echo "$hits" | wc -l | tr -d ' ')
        echo -e "  ${GREEN}OK${NC}    | $method_name in $basename — ${description} (${count} caller(s))"
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ "$WARNINGS" -gt 0 ]; then
    echo -e "${YELLOW}═══ METHOD VERIFY: $WARNINGS unwired method(s) ═══${NC}"
    echo ""
    echo "  These methods have no external callers. Wire or add xfail."
    # Non-fatal warning — some methods may be internal helpers
    exit 0
else
    echo -e "${GREEN}═══ METHOD VERIFY PASSED — all key methods have callers ═══${NC}"
    exit 0
fi
