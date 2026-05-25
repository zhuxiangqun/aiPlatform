#!/bin/bash

# aiPlat-platform 停止脚本
set +e

echo "============================================================"
echo "  aiPlat-platform - 停止服务"
echo "============================================================"

# 读取 PID 文件
AIPLAT_HOME="${AIPLAT_HOME:-$PWD/.aiplat}"
PID_FILE="$AIPLAT_HOME/logs/pids.txt"
[ -f "$PID_FILE" ] && PIDS=$(cat "$PID_FILE")

# 停止所有进程
for pid in $PIDS; do
    if kill -0 $pid 2>/dev/null; then
        kill $pid && echo "✓ 已停止 PID: $pid"
    fi
done

# 确保 uvicorn, frontend 进程都停止
pkill -f "uvicorn.*8002" 2>/dev/null && echo "✓ 已停止 aiPlat-core"
pkill -f "uvicorn.*8001" 2>/dev/null && echo "✓ 已停止 aiPlat-infra"
pkill -f "uvicorn.*8003" 2>/dev/null && echo "✓ 已停止 aiPlat-platform"
pkill -f "uvicorn.*8004" 2>/dev/null && echo "✓ 已停止 aiPlat-app"
pkill -f "uvicorn.*8000" 2>/dev/null && echo "✓ 已停止 aiPlat-management"
pkill -f "mineru-api" 2>/dev/null && echo "✓ 已停止 mineru-api"
pkill -f "proxy_server.py" 2>/dev/null && echo "✓ 已停止前端"
pkill -f "vite.*5173" 2>/dev/null && echo "✓ 已停止 vite(5173)"

sleep 1

# 强制清理残留端口
for port in 8010 8002 8001 8003 8004 8000 5173; do
    pid=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null && echo "✓ 强制停止端口 $port"
    fi
done

# 清理
rm -f "$PID_FILE"

echo ""
echo "============================================================"
echo "  ✓ 已停止所有服务"
echo "============================================================"
