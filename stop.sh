#!/bin/bash

# aiPlat-platform 停止脚本
set +e

echo "============================================================"
echo "  aiPlat-platform - 停止服务"
echo "============================================================"

# ── 按端口逐个停止 ──
stop_port() {
    local port="$1"
    local name="$2"
    local pid
    # Use explicit TCP port lookup (compatible with macOS and Linux)
    pid=$(lsof -i TCP:$port -t 2>/dev/null | head -1)
    if [ -n "$pid" ]; then
        kill $pid 2>/dev/null
        sleep 0.5
        kill -9 $pid 2>/dev/null 2>/dev/null
        echo "✓ 已停止 $name (端口 $port)"
    else
        # Retry with alternative lsof syntax
        pid=$(lsof -ti :$port 2>/dev/null | head -1)
        if [ -n "$pid" ]; then
            kill $pid 2>/dev/null
            sleep 0.5
            kill -9 $pid 2>/dev/null 2>/dev/null
            echo "✓ 已停止 $name (端口 $port)"
        else
            echo "  $name (端口 $port) 未运行"
        fi
    fi
}

stop_port 8000 "aiPlat-management"
stop_port 8001 "aiPlat-infra"
stop_port 8002 "aiPlat-core"
stop_port 8003 "aiPlat-platform"
stop_port 8004 "aiPlat-app"
stop_port 8010 "mineru-api"
stop_port 5173 "前端 (Vite/proxy)"

# ── 兜底：pkill 清理残留 ──
pkill -f "core/server.py" 2>/dev/null
pkill -f "mineru-api" 2>/dev/null
pkill -f "proxy_server.py" 2>/dev/null

# ── 清理 PID 文件 ──
AIPLAT_HOME="${AIPLAT_HOME:-$PWD/.aiplat}"
rm -f "$AIPLAT_HOME/logs/pids.txt"

echo ""
echo "============================================================"
echo "  ✓ 已停止所有服务"
echo "============================================================"
