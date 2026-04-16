#!/bin/bash

# aiPlat-management 停止脚本
# 停止所有服务（前端、management、infra）

echo "============================================================"
echo "  aiPlat-platform - 停止服务"
echo "============================================================"
echo ""

# 读取 PID 文件
INFRA_PID_FILE="/tmp/aiplat-infra.pid"
CORE_PID_FILE="/tmp/aiplat-core.pid"
MGMT_PID_FILE="/tmp/aiplat-management.pid"
FRONTEND_PID_FILE="/tmp/aiplat-frontend.pid"

# 停止 management 层
echo "停止 aiPlat-management..."
if [ -f "$MGMT_PID_FILE" ]; then
    MGMT_PID=$(cat "$MGMT_PID_FILE")
    if kill -0 $MGMT_PID 2>/dev/null; then
        kill $MGMT_PID && echo "  ✓ 已停止 aiPlat-management (PID: $MGMT_PID)"
    fi
    rm -f "$MGMT_PID_FILE"
else
    # 尝试查找进程
    MGMT_PID=$(pgrep -f "uvicorn management.server" 2>/dev/null)
    if [ -n "$MGMT_PID" ]; then
        kill $MGMT_PID && echo "  ✓ 已停止 aiPlat-management (PID: $MGMT_PID)"
    else
        echo "  - aiPlat-management 未运行"
    fi
fi

# 停止 core 层
echo "停止 aiPlat-core..."
if [ -f "$CORE_PID_FILE" ]; then
    CORE_PID=$(cat "$CORE_PID_FILE")
    if kill -0 $CORE_PID 2>/dev/null; then
        kill $CORE_PID && echo "  ✓ 已停止 aiPlat-core (PID: $CORE_PID)"
    fi
    rm -f "$CORE_PID_FILE"
else
    CORE_PID=$(pgrep -f "uvicorn core.server:app" 2>/dev/null)
    if [ -n "$CORE_PID" ]; then
        kill $CORE_PID && echo "  ✓ 已停止 aiPlat-core (PID: $CORE_PID)"
    else
        echo "  - aiPlat-core 未运行"
    fi
fi

# 停止 infra 层
echo "停止 aiPlat-infra..."
if [ -f "$INFRA_PID_FILE" ]; then
    INFRA_PID=$(cat "$INFRA_PID_FILE")
    if kill -0 $INFRA_PID 2>/dev/null; then
        kill $INFRA_PID && echo "  ✓ 已停止 aiPlat-infra (PID: $INFRA_PID)"
    fi
    rm -f "$INFRA_PID_FILE"
else
    # 尝试查找进程
    INFRA_PID=$(pgrep -f "infra.management.api.run_server" 2>/dev/null)
    if [ -n "$INFRA_PID" ]; then
        kill $INFRA_PID && echo "  ✓ 已停止 aiPlat-infra (PID: $INFRA_PID)"
    else
        echo "  - aiPlat-infra 未运行"
    fi
fi

# 停止前端
echo "停止前端..."
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID && echo "  ✓ 已停止前端 (PID: $FRONTEND_PID)"
    fi
    rm -f "$FRONTEND_PID_FILE"
else
    FRONTEND_PID=$(pgrep -f "vite" 2>/dev/null)
    if [ -n "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID && echo "  ✓ 已停止前端 (PID: $FRONTEND_PID)"
    else
        echo "  - 前端未运行"
    fi
fi

# 清理
rm -f /tmp/aiplat-infra.pid
rm -f /tmp/aiplat-core.pid
rm -f /tmp/aiplat-management.pid
rm -f /tmp/aiplat-frontend.pid

# 检查端口
echo ""
echo "检查端口状态..."
INFRA_PORT=$(lsof -i :8001 2>/dev/null | grep LISTEN || echo "")
CORE_PORT=$(lsof -i :8002 2>/dev/null | grep LISTEN || echo "")
MGMT_PORT=$(lsof -i :8000 2>/dev/null | grep LISTEN || echo "")
FRONTEND_PORT=$(lsof -i :5173 2>/dev/null | grep LISTEN || echo "")

if [ -z "$INFRA_PORT" ] && [ -z "$CORE_PORT" ] && [ -z "$MGMT_PORT" ] && [ -z "$FRONTEND_PORT" ]; then
    echo ""
    echo "============================================================"
    echo "  ✓ 所有服务已停止"
    echo "============================================================"
else
    echo ""
    echo "============================================================"
    echo "  ⚠ 部分端口可能仍被占用"
    echo "============================================================"
    [ -n "$INFRA_PORT" ] && echo "  端口 8001 仍被占用"
    [ -n "$CORE_PORT" ] && echo "  端口 8002 仍被占用"
    [ -n "$MGMT_PORT" ] && echo "  端口 8000 仍被占用"
    [ -n "$FRONTEND_PORT" ] && echo "  端口 5173 仍被占用"
    echo ""
    echo "可以使用以下命令强制停止:"
    echo "  kill -9 \$(lsof -t -i:8001)  # infra"
    echo "  kill -9 \$(lsof -t -i:8002)  # core"
    echo "  kill -9 \$(lsof -t -i:8000)  # management"
    echo "  kill -9 \$(lsof -t -i:5173)  # frontend"
fi
