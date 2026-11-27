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
# $3=empty_ok_msg：端口已空时打印该成功文案（用于 8010 已被 local_proxy_down 释放的场景）
wait_port_free() {
    local port="$1"
    local tries="${2:-10}"
    local i
    for i in $(seq 1 "$tries"); do
        if ! lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.3
    done
    return 1
}

stop_port() {
    local port="$1"
    local name="$2"
    local empty_ok_msg="${3:-}"
    local pids
    # Prefer LISTEN holders (master/worker). Fall back to any fd on the port.
    pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [ -z "$pids" ]; then
        pids=$(lsof -ti :"$port" 2>/dev/null | grep -v "^$(pgrep -x 'clash-meta' 2>/dev/null || echo '99999')$" || true)
    fi
    if [ -n "$pids" ]; then
        for pid in $pids; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 0.5
        for pid in $pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
        if wait_port_free "$port" 15; then
            echo "✓ 已停止 $name (端口 $port)"
        else
            echo "⚠ $name 端口 $port 仍有监听进程，请检查: lsof -nP -iTCP:$port -sTCP:LISTEN"
        fi
    elif [ -n "$empty_ok_msg" ]; then
        echo "✓ $empty_ok_msg"
    else
        echo "  $name (端口 $port) 未运行"
    fi
}

# Eval local proxy (API + worker) before freeing :8010 for mineru.
# Pidfile stop is the primary path; stop_port 8010/8011 below is orphan/mineru sweep only.
EVAL_PORT="${AIPLAT_EVAL_PORT:-8010}"
if [ -f "$PROJECT_ROOT/packages/aiplat-evaluation/scripts/local_proxy_down.sh" ]; then
  echo "── eval local proxy (:${EVAL_PORT} + worker) ──"
  bash "$PROJECT_ROOT/packages/aiplat-evaluation/scripts/local_proxy_down.sh" 2>/dev/null || true
fi

stop_port 8000 "aiPlat-management"
stop_port 8001 "aiPlat-infra"
stop_port 8002 "aiPlat-core"
stop_port 8003 "aiPlat-platform"
stop_port 8004 "aiPlat-app"
# Sweep after local_proxy_down: empty port is success (already freed), not "未运行"
stop_port 8010 "mineru-api / eval-api" "端口 8010 已空（eval proxy 已停 / 无 mineru 残留）"
stop_port 8011 "eval-api (alt)" "端口 8011 已空（无残留）"
stop_port 5173 "前端 (Vite/proxy)"

# ── 兜底：pkill 清理残留（含 gunicorn worker；仅杀 port 可能漏 master）──
pkill -f "core/server.py" 2>/dev/null || true
pkill -f "gunicorn -c gunicorn.conf.py" 2>/dev/null || true
pkill -f "gunicorn.*server:app" 2>/dev/null || true
pkill -f "gunicorn.*infra.management.api.main" 2>/dev/null || true
pkill -f "gunicorn.*api.rest.routes:app" 2>/dev/null || true
pkill -f "gunicorn.*management.server" 2>/dev/null || true
pkill -f "mineru-api" 2>/dev/null || true
pkill -f "proxy_server.py" 2>/dev/null || true
pkill -f "app.worker" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
# Re-check critical ports after pkill
for port in 8000 8001 8002 8003 8004 5173; do
    if lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null || true
    fi
done

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
