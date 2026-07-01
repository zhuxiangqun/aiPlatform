#!/usr/bin/env bash
# run_e2e.sh — 一键 E2E 测试: 启动→等待→测试→清理
#
# 用法:
#   bash scripts/run_e2e.sh
#
# 前提: docker compose 可用, aiplat-* 镜像已构建
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[0;32m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  aiPlatform E2E 全域测试${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Step 1: Start services
echo -e "${BLUE}[1/4] 启动测试服务...${NC}"
cd "$WORKSPACE"
docker compose -f docker-compose.test.yml down -v 2>/dev/null || true
docker compose -f docker-compose.test.yml up -d 2>&1 | tail -3
echo ""

# Step 2: Wait for health
echo -e "${BLUE}[2/4] 等待服务就绪...${NC}"
if bash "$SCRIPT_DIR/wait_for_health.sh" 60; then
    echo ""
else
    echo -e "${RED}❌ 服务未就绪，放弃测试${NC}"
    docker compose -f docker-compose.test.yml down 2>/dev/null
    exit 1
fi

# Step 3: Run tests
echo -e "${BLUE}[3/4] 运行 E2E 测试...${NC}"
cd "$WORKSPACE"
if python3 -m pytest tests/e2e/ -v --tb=short 2>&1; then
    TEST_RESULT=0
    echo -e "${GREEN}✅ 所有 E2E 测试通过${NC}"
else
    TEST_RESULT=1
    echo -e "${RED}❌ E2E 测试失败${NC}"
fi

# Step 4: Cleanup
echo ""
echo -e "${BLUE}[4/4] 清理...${NC}"
docker compose -f docker-compose.test.yml down -v 2>&1 | tail -2

echo ""
if [ "$TEST_RESULT" -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  E2E 全域测试: 全部通过${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  E2E 全域测试: 失败${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
fi

exit $TEST_RESULT
