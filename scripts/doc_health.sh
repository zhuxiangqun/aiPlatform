#!/usr/bin/env bash
# doc_health.sh — 一键运行所有文档健康检查
#
# 用法:
#   bash scripts/doc_health.sh
#
# 检查项:
#   1. CAPABILITIES 统计表一致性 (章节 ✅ 计数 vs 统计表)
#   2. 代码-文档能力缺口 (新模块未登记)
#   3. 文档同步 (verify_doc_sync.sh 完整流程)
#   4. CLAUDE.md 状态节回归 (状态型 §5.NNN 应迁往 PHASE_STATUS.md) + 体量监视
#
# 退出码: 0=全部通过, 1=有需修复项
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
PASS=0; FAIL=0

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  aiPlatform 文档健康检查${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check 1: Capability count consistency
echo -e "${YELLOW}[1/4] CAPABILITIES 统计表一致性${NC}"
if python3 "$WORKSPACE/scripts/verify_capability_consistency.py" 2>&1; then
    echo -e "${GREEN}  ✅ 通过${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}  ❌ 不一致 — 请更新统计表${NC}"
    FAIL=$((FAIL + 1))
fi

# Check 2: Code-doc gap
echo ""
echo -e "${YELLOW}[2/4] 代码-文档能力缺口${NC}"
if python3 "$WORKSPACE/scripts/check_code_doc_gap.py" 2>&1; then
    echo -e "${GREEN}  ✅ 通过${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}  ❌ 有缺口 — 请在 CAPABILITIES 中登记新模块${NC}"
    FAIL=$((FAIL + 1))
fi

# Check 3: Full doc sync (diff-based)
echo ""
echo -e "${YELLOW}[3/4] 文档同步（diff 检测）${NC}"
if bash "$WORKSPACE/scripts/verify_doc_sync.sh" 2>&1; then
    echo -e "${GREEN}  ✅ 通过${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}  ❌ 文档未同步${NC}"
    FAIL=$((FAIL + 1))
fi

# Check 4: CLAUDE.md 状态节回归 + 体量监视 (P2a 分流守卫)
echo ""
echo -e "${YELLOW}[4/4] CLAUDE.md 状态节回归 + 体量${NC}"
CLAUDE_LINES=$(wc -l < "$WORKSPACE/aiPlat-core/CLAUDE.md" | tr -d ' ')
if python3 "$WORKSPACE/scripts/guard_claude_status.py" --check 2>&1 && [ "$CLAUDE_LINES" -le 2000 ]; then
    echo -e "${GREEN}  ✅ 通过 (CLAUDE.md ${CLAUDE_LINES} 行, 无状态节回归)${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}  ❌ 状态节回归 或 CLAUDE.md 超 2000 行 (${CLAUDE_LINES}) — 迁往 docs/PHASE_STATUS.md${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}  全部通过: $PASS/$((PASS + FAIL))${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 0
else
    echo -e "${RED}  $FAIL 项失败 / $((PASS + FAIL)) 项${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi
