#!/bin/bash

# aiPlat-platform 停止脚本（与 start.sh 同根目录；cwd 无关）
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
# Must match start.sh default — eval pid files live under $AIPLAT_HOME/logs
AIPLAT_HOME="${AIPLAT_HOME:-$HOME/.aiplat}"
export AIPLAT_HOME
export AIPLAT_EVAL_PID_DIR="${AIPLAT_EVAL_PID_DIR:-$AIPLAT_HOME/logs}"

echo "============================================================"
echo "  aiPlat-platform - 停止服务"
echo "============================================================"

# ── 按端口逐个停止 ──
stop_port() {
    local port="$1"
    local name="$2"
    local pids
    # Kill ALL processes tied to this port (LISTEN + ESTABLISHED workers)
    pids=$(lsof -ti :$port 2>/dev/null | grep -v "^$(pgrep -x 'clash-meta' 2>/dev/null || echo '99999')$" || true)
    if [ -n "$pids" ]; then
        for pid in $pids; do
            kill $pid 2>/dev/null
        done
        sleep 0.5
        for pid in $pids; do
            kill -9 $pid 2>/dev/null 2>/dev/null
        done
        echo "✓ 已停止 $name (端口 $port)"
    else
        echo "  $name (端口 $port) 未运行"
    fi
}

# Eval local proxy (API + worker) before freeing :8010 for mineru
if [ -f "$PROJECT_ROOT/packages/aiplat-evaluation/scripts/local_proxy_down.sh" ]; then
  bash "$PROJECT_ROOT/packages/aiplat-evaluation/scripts/local_proxy_down.sh" 2>/dev/null || true
fi

stop_port 8000 "aiPlat-management"
stop_port 8001 "aiPlat-infra"
stop_port 8002 "aiPlat-core"
stop_port 8003 "aiPlat-platform"
stop_port 8004 "aiPlat-app"
stop_port 8010 "mineru-api / eval-api"
stop_port 8011 "eval-api (alt)"
stop_port 5173 "前端 (Vite/proxy)"

# ── 兜底：pkill 清理残留 ──
pkill -f "core/server.py" 2>/dev/null
pkill -f "mineru-api" 2>/dev/null
pkill -f "proxy_server.py" 2>/dev/null
pkill -f "app.worker" 2>/dev/null
pkill -f "uvicorn app.main:app" 2>/dev/null

# ── Stop Enterprise Gateway ──
pkill -f "gateway.*8005\|enterprise.*gateway" 2>/dev/null
lsof -ti:8005 2>/dev/null | xargs kill 2>/dev/null

# ── 清理 PID 文件 ──
rm -f "$AIPLAT_HOME/logs/pids.txt"
rm -f "$AIPLAT_EVAL_PID_DIR/eval-api.pid" "$AIPLAT_EVAL_PID_DIR/eval-worker.pid"

echo ""
echo "============================================================"
echo "  ✓ 已停止所有服务"
echo "============================================================"
