#!/bin/bash

# aiPlat-infra 停止脚本

echo "============================================================"
echo "  aiPlat-infra - 停止服务"
echo "============================================================"
echo ""

# 读取 PID 文件
PID_FILE="/tmp/aiplat-infra.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 $PID 2>/dev/null; then
        kill $PID && echo "  ✓ 已停止服务 (PID: $PID)"
    else
        echo "  - 服务未运行"
    fi
    rm -f "$PID_FILE"
else
    # 尝试查找进程
    PID=$(pgrep -f "infra.management.api.run_server" 2>/dev/null)
    if [ -n "$PID" ]; then
        kill $PID && echo "  ✓ 已停止服务 (PID: $PID)"
    else
        echo "  - 服务未运行"
    fi
fi

# 检查端口
PORT=$(lsof -i :8001 2>/dev/null | grep LISTEN || echo "")
if [ -n "$PORT" ]; then
    echo "  ⚠ 端口 8001 仍被占用"
fi

echo ""
echo "============================================================"
echo "  ✓ 服务已停止"
echo "============================================================"