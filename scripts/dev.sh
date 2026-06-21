#!/bin/bash
# aiplat dev — 统一启动所有开发服务
#
# 用法:  bash scripts/dev.sh [服务名...]
# 示例:  bash scripts/dev.sh              # 启动全部 5 个服务
#        bash scripts/dev.sh core frontend # 只启动 core + 前端
#
# 服务映射:
#   core       → aiPlat-core (8002)
#   management → aiPlat-management (8000)
#   platform   → aiPlat-platform (8003)
#   app        → aiPlat-app (8004)
#   frontend   → Vite dev server (5173)
#
# 环境变量 (可选):
#   AIPLAT_CORE_PORT=8002
#   AIPLAT_MGMT_PORT=8000
#   AIPLAT_PLATFORM_PORT=8003
#   AIPLAT_APP_PORT=8004
#   AIPLAT_FRONTEND_PORT=5173
#   AIPLAT_SKIP_FRONTEND=1    # 跳过 npm install

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── 端口 ──
CORE_PORT="${AIPLAT_CORE_PORT:-8002}"
MGMT_PORT="${AIPLAT_MGMT_PORT:-8000}"
PLATFORM_PORT="${AIPLAT_PLATFORM_PORT:-8003}"
APP_PORT="${AIPLAT_APP_PORT:-8004}"
FRONTEND_PORT="${AIPLAT_FRONTEND_PORT:-5173}"

# ── 要启动的服务 ──
if [ $# -eq 0 ]; then
    SERVICES="core management platform app frontend"
else
    SERVICES="$*"
fi

cleanup() {
    echo -e "\n${YELLOW}⏹  正在停止所有服务...${NC}"
    if [ -n "$CORE_PID" ]; then kill $CORE_PID 2>/dev/null; fi
    if [ -n "$MGMT_PID" ]; then kill $MGMT_PID 2>/dev/null; fi
    if [ -n "$PLATFORM_PID" ]; then kill $PLATFORM_PID 2>/dev/null; fi
    if [ -n "$APP_PID" ]; then kill $APP_PID 2>/dev/null; fi
    if [ -n "$VITE_PID" ]; then kill $VITE_PID 2>/dev/null; fi
    wait 2>/dev/null
    echo -e "${GREEN}✓ 已停止${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   aiplat dev — 启动开发环境${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Core (8002) ──
if echo "$SERVICES" | grep -qw "core"; then
    echo -e "${GREEN}▶  启动 aiPlat-core${NC} (端口 $CORE_PORT)"
    cd "$REPO_ROOT"
    python aiPlat-core/core/server.py &
    CORE_PID=$!
    echo "   PID=$CORE_PID"
fi

# ── Management (8000) ──
if echo "$SERVICES" | grep -qw "management"; then
    echo -e "${GREEN}▶  启动 aiPlat-management${NC} (端口 $MGMT_PORT)"
    cd "$REPO_ROOT/aiPlat-management"
    python management/main.py &
    MGMT_PID=$!
    echo "   PID=$MGMT_PID"
fi

# ── Platform (8003) ──
if echo "$SERVICES" | grep -qw "platform"; then
    echo -e "${GREEN}▶  启动 aiPlat-platform${NC} (端口 $PLATFORM_PORT)"
    cd "$REPO_ROOT/aiPlat-platform"
    python api/rest/routes.py &
    PLATFORM_PID=$!
    echo "   PID=$PLATFORM_PID"
fi

# ── App (8004) ──
if echo "$SERVICES" | grep -qw "app"; then
    echo -e "${GREEN}▶  启动 aiPlat-app${NC} (端口 $APP_PORT)"
    cd "$REPO_ROOT/aiPlat-app"
    if [ -f "main.py" ]; then
        uvicorn main:app --host 0.0.0.0 --port $APP_PORT &
        APP_PID=$!
    else
        echo -e "${YELLOW}   ⚠  aiPlat-app 目录无 main.py，跳过${NC}"
    fi
fi

# ── Frontend (5173) ──
if echo "$SERVICES" | grep -qw "frontend"; then
    if [ "${AIPLAT_SKIP_FRONTEND:-0}" != "1" ]; then
        echo -e "${GREEN}▶  启动 Vite 前端${NC} (端口 $FRONTEND_PORT)"
        cd "$REPO_ROOT/aiPlat-management/frontend"
        if [ ! -d "node_modules" ]; then
            echo "   ⏳ npm install (首次)..."
            npm install --silent
        fi
        npx vite --host 0.0.0.0 --port $FRONTEND_PORT &
        VITE_PID=$!
        echo "   PID=$VITE_PID"
    fi
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ 所有服务已启动${NC}"
echo ""
echo "  访问地址:"
[ -n "$CORE_PID" ] && echo "    Core:       http://localhost:$CORE_PORT"
[ -n "$MGMT_PID" ] && echo "    Management: http://localhost:$MGMT_PORT"
[ -n "$PLATFORM_PID" ] && echo "    Platform:   http://localhost:$PLATFORM_PORT"
[ -n "$APP_PID" ] && echo "    App:        http://localhost:$APP_PORT"
[ -n "$VITE_PID" ] && echo "    Frontend:   http://localhost:$FRONTEND_PORT"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── 等待子进程 ──
wait
