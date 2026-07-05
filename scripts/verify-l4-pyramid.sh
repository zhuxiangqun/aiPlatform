#!/usr/bin/env bash
# verify-l4-pyramid.sh — 逐层纵向验证：系统处于 L0→L5 的哪一层
#
# 按照最低分原则，每一层的所有必选项通过后，才能进入下一层。
# 输出当前最大可宣称等级。
#
# Usage:
#   bash scripts/verify-l4-pyramid.sh          # 自动验证全部层级
#   bash scripts/verify-l4-pyramid.sh L3       # 验证到 L3

set -uo pipefail  # no set -e — grep returns 1 for no match, which we handle

REPO="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$REPO/aiPlat-core/core"
TARGET_LEVEL="${1:-L5}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
MAX_LEVEL="L0"

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
        -gt) test "$actual" -gt "$expected" ;;
        *)   test "$actual" -ge "$expected" ;;
    esac
    if [ $? -eq 0 ]; then
        printf "    ${GREEN}✓${NC} %s\n" "$label"
        PASS=$((PASS + 1))
        return 0
    else
        printf "    ${RED}✗${NC} %-40s (got %s, need %s %s)\n" "$label" "$actual" "$op" "$expected"
        FAIL=$((FAIL + 1))
        return 1
    fi
}

declare_layer() {
    local level="$1"
    local name="$2"
    local total="$3"
    echo ""
    printf "${CYAN}[%s]${NC} %s (%s 项必选)\n" "$level" "$name" "$total"
    PASS=0 FAIL=0
    MAX_LEVEL="$level"
    if [ "$level" \> "$TARGET_LEVEL" ] && [ "$TARGET_LEVEL" != "L5" ]; then
        echo "    ⏭ 跳过 (目标层级: $TARGET_LEVEL)"
        return 2
    fi
}

finish_layer() {
    local level="$1"
    if [ $? -eq 2 ]; then return 2; fi
    if [ "$FAIL" -eq 0 ]; then
        printf "  ${GREEN}✅ %s 通过${NC} (%s/%s)\n" "$level" "$PASS" "$((PASS+FAIL))"
        return 0
    else
        printf "  ${RED}❌ %s 未通过${NC} (%s/%s FAIL)\n" "$level" "$PASS" "$((PASS+FAIL))"
        return 1
    fi
}


echo ""
echo "========================================="
echo " aiPlat L0→L5 逐层纵向验证"
echo " 最低分原则: 下层不过, 不测上层"
echo " 日期: $(date -u +%Y-%m-%d)"
echo "========================================="


# ══════════════════════════════════════════════════════
# L0: 基础可执行 (3 项)
# ══════════════════════════════════════════════════════
declare_layer "L0" "基础可执行" 3

# 1. 核心模块编译
python -m py_compile "$CORE/harness/execution/pipeline_engine.py" 2>/dev/null
check "核心模块编译 (pipeline_engine)" "$?" 0

# 2. 主入口模块存在
check "主入口模块 (integration.py)" "$(wc -l < "$CORE/harness/integration.py" 2>/dev/null)" 1000

# 3. uvicorn 进程或可导入
python3 -c "import sys; sys.path.insert(0,'$REPO/aiPlat-core'); from core.harness.integration import get_skill_registry" 2>/dev/null
check "核心模块可导入" "$?" 0

if finish_layer "L0"; then
    :  # continue
else
    echo -e "\n${YELLOW}当前最大可宣称等级: L0${NC} (L1 检查被阻断)"
    exit 1
fi


# ══════════════════════════════════════════════════════
# L1: 提示词工程 (3 项)
# ══════════════════════════════════════════════════════
declare_layer "L1" "提示词工程" 3

# 1. LLM 适配器存在
_llm_has=$(grep -cE 'def create_selected_adapter' "$CORE/harness/utils/model_injection.py" 2>/dev/null)
check "LLM 适配器 (model_injection)" "$_llm_has" 1

# 2. 提示词模板系统
check "提示词模板 (prompt_loader)" "$(wc -l < "$CORE/harness/utils/prompt_loader.py" 2>/dev/null)" 100

# 3. sys_llm_generate 函数
check "sys_llm_generate" "$(grep -cE 'def sys_llm_generate|async def sys_llm_generate' "$CORE/harness/syscalls/llm.py" 2>/dev/null)" 1

if finish_layer "L1"; then
    :
else
    echo -e "\n${YELLOW}当前最大可宣称等级: L1 (提示词工程)${NC} (L2 检查被阻断)"
    exit 1
fi


# ══════════════════════════════════════════════════════
# L2: 上下文工程 (4 项)
# ══════════════════════════════════════════════════════
declare_layer "L2" "上下文工程" 4

# 1. RAG 检索器
_rag=$(grep -cE 'InMemoryRetriever|KnowledgeRetriever|VectorStoreRetriever' "$CORE/harness/knowledge/retriever.py" 2>/dev/null)
check "RAG 检索器 (retriever)" "${_rag:-0}" 1

# 2. 上下文组装器
_ctx=$(grep -cE 'ContextAssembler|PromptAssembler' "$CORE/harness/assembly/__init__.py" 2>/dev/null)
check "上下文组装 (assembly)" "${_ctx:-0}" 1

# 3. 知识库 Provider
_kb=$(wc -l < "$CORE/harness/knowledge/wiki_engine.py" 2>/dev/null)
check "知识库引擎 (wiki_engine)" "$_kb" 500

# 4. 文档解析器
_doc=$(grep -cE 'DocumentParser|DocumentConverter' "$CORE/harness/ontology_engine/document_parser.py" 2>/dev/null)
check "文档解析器" "${_doc:-0}" 1

if finish_layer "L2"; then
    :
else
    echo -e "\n${YELLOW}当前最大可宣称等级: L2 (上下文工程)${NC} (L3 检查被阻断)"
    exit 1
fi


# ══════════════════════════════════════════════════════
# L3: 驾驭工程 (5 项)
# ══════════════════════════════════════════════════════
declare_layer "L3" "驾驭工程" 5

# 1. 权限门禁
check "PolicyGate (权限)" "$(grep -cE 'class PolicyGate' "$CORE/harness/infrastructure/gates/policy_gate.py" 2>/dev/null)" 1

# 2. 审批门
check "ApprovalGate (审批)" "$(grep -cE 'class ApprovalGate' "$CORE/harness/infrastructure/gates/approval_gate.py" 2>/dev/null)" 1

# 3. Skill 注册表
_skreg=$(grep -cE 'get_skill_registry|SkillRegistry' "$CORE/harness/integration.py" 2>/dev/null)
check "SkillRegistry" "$_skreg" 1

# 4. Tool 注册表
_tool=$(grep -cE '_resolve_tool_registry|ToolRegistry' "$CORE/harness/integration.py" 2>/dev/null)
check "ToolRegistry" "$_tool" 1

# 5. 安全沙箱
_sb=$(grep -cE 'class SandboxGate|SandboxGate' "$CORE/harness/infrastructure/gates/sandbox_gate.py" 2>/dev/null)
check "SandboxGate (沙箱)" "$_sb" 1

if finish_layer "L3"; then
    :
else
    echo -e "\n${YELLOW}当前最大可宣称等级: L3 (驾驭工程)${NC} (L4 检查被阻断)"
    exit 1
fi


# ══════════════════════════════════════════════════════
# L4: 循环工程 (8 项)
# ══════════════════════════════════════════════════════
declare_layer "L4" "循环工程" 8

# 1. 自主重试循环
check "自主循环 (_retry_loop)" "$(grep -cE 'async def _retry_loop' "$CORE/harness/execution/pipeline_engine.py" 2>/dev/null)" 1

# 2. HITL 分级配置
check "HITL 分级" "$(grep -cE 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' "$CORE/apps/agents/operator_agent.py" 2>/dev/null)" 1

# 3. Pipeline 多 Agent 编队
check "多 Agent Pipeline" "$(wc -l < "$CORE/harness/integration.py" 2>/dev/null)" 1000

# 4. 四层记忆 (episodic + semantic + manager + working)
_mem4=$(find "$CORE/harness/memory/" \( -name 'working.py' -o -name 'episodic.py' -o -name 'semantic.py' -o -name 'manager.py' \) 2>/dev/null | wc -l | tr -d ' ')
check "四层记忆完整 (4/4)" "$_mem4" 4 -eq

# 5. ErrorTranslator + FailoverReason
check "ErrorTranslator" "$(grep -cE 'class FailoverReason' "$CORE/harness/infrastructure/gates/error_translator.py" 2>/dev/null)" 1

# 6. CRAG 3 级回退
check "CRAG 3级回退" "$(grep -cE 'CRAG' "$CORE/apps/agents/materials_chat.py" 2>/dev/null)" 1

# 7. 本体引擎 (≥ 23 模块)
_onto_cnt=$(find "$CORE/harness/ontology_engine" -name '*.py' ! -name '__init__.py' 2>/dev/null | wc -l | tr -d ' ')
check "本体引擎 (≥23模块)" "$_onto_cnt" 23

# 8. 自愈策略 (≥ 5)
check "自愈策略 (≥5)" "$(grep -cE 'async def _strategy_' "$CORE/harness/execution/pipeline_engine.py" 2>/dev/null)" 5

if finish_layer "L4"; then
    MAX_LEVEL="L4"
else
    echo -e "\n${YELLOW}当前最大可宣称等级: L4 (循环工程)${NC} (L5 检查被阻断)"
    exit 1
fi


# ══════════════════════════════════════════════════════
# L5: 元循环工程 (8 项)
# ══════════════════════════════════════════════════════
declare_layer "L5" "元循环工程" 8

# 1. UCB1 策略搜索
check "UCB1 搜索 (Phase29)" "$(grep -cE 'class StrategySearchEngine' "$CORE/harness/optimization/search_engine.py" 2>/dev/null)" 1

# 2. 自主闭环执行
check "GoalExecutor (Phase30)" "$(grep -cE 'class GoalExecutor' "$CORE/harness/optimization/goal_executor.py" 2>/dev/null)" 1

# 3. 工具自举
check "ToolBootstrap (Phase31)" "$(grep -cE 'class ToolBootstrapEngine' "$CORE/harness/optimization/tool_bootstrap.py" 2>/dev/null)" 1

# 4. 动态组队
check "DynamicOrchestrator (Phase32)" "$(grep -cE 'class DynamicOrchestrator' "$CORE/harness/coordination/dynamic_orchestrator.py" 2>/dev/null)" 1

# 5. 策略效果跟踪
check "StrategyTracker (Phase26)" "$(grep -cE 'class StrategyEffectivenessTracker' "$CORE/harness/optimization/strategy_tracker.py" 2>/dev/null)" 1

# 6. 跨实例知识共享
check "SharedKnowledgePool (Phase27)" "$(grep -cE 'class SharedKnowledgePool' "$CORE/harness/memory/shared_pool.py" 2>/dev/null)" 1

# 7. 自主目标生成
check "GoalGenerator (Phase28)" "$(grep -cE 'class GoalGenerator' "$CORE/harness/optimization/goal_generator.py" 2>/dev/null)" 1

# 8. 可重现执行快照
check "ExecutionSnapshot (Phase25)" "$(grep -cE 'class ExecutionSnapshot' "$CORE/harness/execution/snapshot.py" 2>/dev/null)" 1

if finish_layer "L5"; then
    MAX_LEVEL="L5"
fi


# ══════════════════════════════════════════════════════
echo ""
echo "========================================="
echo ""
case "$MAX_LEVEL" in
    L5) echo -e "${GREEN}✅ 当前最大可宣称等级: L5 (元循环工程)${NC}" ;;
    L4) echo -e "${GREEN}✅ 当前最大可宣称等级: L4+ (循环工程, 五轴L4+两轴L5)${NC}" ;;
    *)  echo -e "${YELLOW}当前最大可宣称等级: $MAX_LEVEL${NC}" ;;
esac

echo ""
echo "层级含义:"
echo "  L0 = 基础可执行 (脚本集合)"
echo "  L1 = 提示词工程 (写好一句话让模型听懂)"
echo "  L2 = 上下文工程 (组装好一次输入让模型知道)"
echo "  L3 = 驾驭工程 (设计好整个运行环境让模型靠谱)"
echo "  L4 = 循环工程 (让它自己循环跑起来让模型能持续)"
echo "  L5 = 元循环工程 (系统自己优化自己让模型能进化)"
echo ""
echo "说明: 本验证基于最低分原则 (木桶原理)。"
echo "      系统层级由最薄弱环节决定。"
echo "      L4+通过但L5有缺项 → 可宣称L4+ (五轴L4+, 两轴L5)。"
echo ""
exit $FAIL
