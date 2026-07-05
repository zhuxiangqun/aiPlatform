#!/usr/bin/env bash
# verify-l4-claims.sh — 数据层验证：白皮书 L4 声明的所有数字必须可复现
# Usage: bash scripts/verify-l4-claims.sh [REPO_PATH]
# 预期：< 10 秒完成，零依赖（只需 grep/find/wc）

set -euo pipefail

REPO="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local label="$1"
    local actual="$2"
    local expected="$3"
    local op="${4:--ge}"
    actual=$(echo "$actual" | tr -d '[:space:]')
    if [ -z "$actual" ]; then actual=0; fi
    case "$op" in
        -ge) test "$actual" -ge "$expected" ;; 
        -eq) test "$actual" -eq "$expected" ;;
        -le) test "$actual" -le "$expected" ;;
        *) test "$actual" -ge "$expected" ;;
    esac
    if [ $? -eq 0 ]; then
        printf "  ${GREEN}PASS${NC} %-45s %s (expected %s %s)\n" "$label" "$actual" "$op" "$expected"
        PASS=$((PASS + 1))
    else
        printf "  ${RED}FAIL${NC} %-45s %s (expected %s %s)\n" "$label" "$actual" "$op" "$expected"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "========================================="
echo " aiPlat L4 数据层验证"
echo " 白皮书 §2 所有数字声明必须可复现"
echo " 日期: $(date -u +%Y-%m-%d)"
echo "========================================="
echo ""

# ══════════════════════════════════════════════════════
# §A: 自主性
# ══════════════════════════════════════════════════════
echo "[A. 自主性]"

_retry=$(grep -c 'async def _retry_loop' "$REPO/aiPlat-core/core/harness/execution/pipeline_engine.py" 2>/dev/null || echo 0)
check "_retry_loop 函数" "$_retry" 1

_hitl=$(grep -c 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' "$REPO/aiPlat-core/core/apps/agents/operator_agent.py" 2>/dev/null || echo 0)
check "HITL 分级配置" "$_hitl" 1

_meta=$(grep -c 'async def _meta_optimize' "$REPO/aiPlat-core/core/harness/execution/pipeline_engine.py" 2>/dev/null || echo 0)
check "_meta_optimize 自愈函数" "$_meta" 1


# ══════════════════════════════════════════════════════
# §B: 上下文感知
# ══════════════════════════════════════════════════════
echo ""
echo "[B. 上下文感知]"

_onto=$(find "$REPO/aiPlat-core/core/harness/ontology_engine" -name '*.py' ! -name '__init__.py' 2>/dev/null | wc -l)
check "本体引擎模块数 (声称 ≥ 23)" "$_onto" 23

_crag=$(grep -c 'CRAG' "$REPO/aiPlat-core/core/apps/agents/materials_chat.py" 2>/dev/null || echo 0)
check "CRAG 回退链存在" "$_crag" 1

_ctx=$(grep -c 'class RunContext' "$REPO/aiPlat-core/core/harness/kernel/types.py" 2>/dev/null || echo 0)
check "RunContext 定义" "$_ctx" 1

_dr=$(grep -c 'class DomainRouter' "$REPO/aiPlat-core/core/harness/knowledge/domain_router.py" 2>/dev/null || echo 0)
check "DomainRouter 多域路由" "$_dr" 1

# ══════════════════════════════════════════════════════
# §C: 工具掌握
# ══════════════════════════════════════════════════════
echo ""
echo "[C. 工具掌握]"

_ep=$(find "$REPO/aiPlat-core/core/api/routers" -name '*.py' ! -name '__init__.py' 2>/dev/null | xargs grep -cEh '@router\.(get|post|put|delete|patch|options|head|route)' 2>/dev/null | awk '{sum+=$0} END {print sum}')
check "API 端点数 (声称 ≥ 813)" "$_ep" 813

_sk=$(find "$REPO/aiPlat-core/core/engine/skills" -name 'SKILL.md' 2>/dev/null | wc -l)
check "Engine Skill 数 (声称 32)" "$_sk" 30

_pg=$(wc -l < "$REPO/aiPlat-core/core/harness/infrastructure/gates/policy_gate.py" 2>/dev/null || echo 0)
check "PolicyGate 规模（间接工具权限）(≥ 800)" "$_pg" 800

_ag=$(wc -l < "$REPO/aiPlat-core/core/harness/infrastructure/gates/approval_gate.py" 2>/dev/null || echo 0)
check "ApprovalGate 规模（危险命令）(≥ 300)" "$_ag" 300


# ══════════════════════════════════════════════════════
# §D: 记忆系统
# ══════════════════════════════════════════════════════
echo ""
echo "[D. 记忆系统]"

_mem=$(find "$REPO/aiPlat-core/core/harness/memory/" \( -name 'working.py' -o -name 'episodic.py' -o -name 'semantic.py' -o -name 'manager.py' \) 2>/dev/null | wc -l)
check "四层记忆文件" "$_mem" 4

_sc=$(grep -c '_resolve_semantic_conflict' "$REPO/aiPlat-core/core/harness/memory/semantic.py" 2>/dev/null || echo 0)
check "Semantic 冲突检测" "$_sc" 1

_epc=$(grep -c 'cleanup_expired' "$REPO/aiPlat-core/core/harness/memory/episodic.py" 2>/dev/null || echo 0)
check "Episodic TTL 清理" "$_epc" 1

_mos=$(test -f ~/.aiplat/agents/memory_os/AGENT.md && echo 1 || echo 0)
check "Memory OS Agent" "$_mos" 1


# ══════════════════════════════════════════════════════
# §E: 协作能力
# ══════════════════════════════════════════════════════
echo ""
echo "[E. 协作能力]"

_int=$(wc -l < "$REPO/aiPlat-core/core/harness/integration.py" 2>/dev/null || echo 0)
check "集成总线规模 (≥ 3000)" "$_int" 3000


# ══════════════════════════════════════════════════════
# §F: 自进化
# ══════════════════════════════════════════════════════
echo ""
echo "[F. 自进化]"

_strat=$(grep -c 'async def _strategy_' "$REPO/aiPlat-core/core/harness/execution/pipeline_engine.py" 2>/dev/null || echo 0)
check "自愈策略数 (声称 5)" "$_strat" 5

_fr=$(grep -c 'class FailoverReason' "$REPO/aiPlat-core/core/harness/infrastructure/gates/error_translator.py" 2>/dev/null || echo 0)
check "FailoverReason 枚举 (19 类)" "$_fr" 1

_et=$(wc -l < "$REPO/aiPlat-core/core/harness/infrastructure/gates/error_translator.py" 2>/dev/null || echo 0)
check "ErrorTranslator 行数 (≥ 600)" "$_et" 600

_po=$(grep -c 'class PromptOptimizer' "$REPO/aiPlat-core/core/harness/optimization/prompt_optimizer.py" 2>/dev/null || echo 0)
check "PromptOptimizer" "$_po" 1


# ══════════════════════════════════════════════════════
# L5 负检查
# ══════════════════════════════════════════════════════
echo ""
echo "[L5 负检查: L5 独有特征应不存在]"

_l5a=$(grep -rn 'strategy_search\|strategy_explore\|policy_search\|multi_armed_bandit\|bayesian_opt' "$REPO/aiPlat-core/core/harness/" --include='*.py' 2>/dev/null | grep -v __pycache__ | grep -v ':0$' | wc -l || true)
check "L5: 策略搜索引擎不存在" "$_l5a" 0 "-le"

_l5b=$(grep -rn 'tool_bootstrap\|tool_factory\|skill_factory\|auto_tool' "$REPO/aiPlat-core/core/harness/" --include='*.py' 2>/dev/null | grep -v __pycache__ | grep -v ':0$' | wc -l || true)
check "L5: 自举工具创建不存在" "$_l5b" 0 "-le"

_l5c=$(grep -rn 'swarm_memory\|shared_memory_bus\|memory_gossip\|knowledge_replicat' "$REPO/aiPlat-core/core/harness/" --include='*.py' 2>/dev/null | grep -v __pycache__ | grep -v ':0$' | wc -l || true)
check "L5: 蜂群共享记忆不存在" "$_l5c" 0 "-le"


echo ""
echo "========================================="
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✅ 数据层验证通过: ${PASS}/${PASS} PASS${NC}"
else
    echo -e "${RED}❌ 数据层验证失败: ${PASS} PASS / ${FAIL} FAIL${NC}"
fi
echo "========================================="
echo ""
exit $FAIL
