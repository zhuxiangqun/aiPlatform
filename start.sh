#!/bin/bash

# aiPlat-platform 三层 + platform/app + 前端 启动脚本
# 启动顺序:
#   aiPlat-core (8002) → aiPlat-infra (8001) → aiPlat-platform (8003) → aiPlat-app (8004) → aiPlat-management (8000) → frontend (5173)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

PY="$PROJECT_ROOT/.venv/bin/python"
PIP="$PROJECT_ROOT/.venv/bin/pip"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
  PIP="$(command -v pip3 || command -v pip)"
fi

echo "============================================================"
echo "  aiPlat-platform - 启动服务"
echo "============================================================"
echo ""
echo "Python: $($PY --version 2>&1 | awk '{print $2}')"
echo ""

# ===== Step 1: aiPlat-core =====
echo "============================================================"
echo "  Step 1/4: 启动 aiPlat-core (端口 8002)"
echo "============================================================"

cd "$PROJECT_ROOT/aiPlat-core/core"
# 确保 ExecutionStore DB 路径稳定（用于 learning_artifacts / approvals 等管理功能）
export AIPLAT_EXECUTION_DB_PATH="${AIPLAT_EXECUTION_DB_PATH:-$PROJECT_ROOT/aiPlat-core/core/data/aiplat_executions.sqlite3}"
mkdir -p "$(dirname "$AIPLAT_EXECUTION_DB_PATH")"
echo "Execution DB: $AIPLAT_EXECUTION_DB_PATH"
PYTHONPATH="$PROJECT_ROOT/aiPlat-core" nohup "$PY" -m uvicorn server:app --host 0.0.0.0 --port 8002 > /tmp/aiplat-core.log 2>&1 &
CORE_PID=$!
echo "PID: $CORE_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8002/api/core/health >/dev/null 2>&1 && echo "✓ aiPlat-core 启动成功 (8002)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 2: aiPlat-infra =====
echo ""
echo "============================================================"
echo "  Step 2/4: 启动 aiPlat-infra (端口 8001)"
echo "============================================================"

cd "$PROJECT_ROOT/aiPlat-infra"
PYTHONPATH="$PROJECT_ROOT/aiPlat-infra" nohup "$PY" -m uvicorn infra.management.api.main:create_app --host 0.0.0.0 --port 8001 --factory > /tmp/aiplat-infra.log 2>&1 &
INFRA_PID=$!
echo "PID: $INFRA_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8001/api/infra/health >/dev/null 2>&1 && echo "✓ aiPlat-infra 启动成功 (8001)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 3: aiPlat-platform =====
echo ""
echo "============================================================"
echo "  Step 3/6: 启动 aiPlat-platform (端口 8003)"
echo "============================================================"

cd "$PROJECT_ROOT/aiPlat-platform"
export AIPLAT_PLATFORM_DB_PATH="${AIPLAT_PLATFORM_DB_PATH:-$PROJECT_ROOT/aiPlat-platform/data/aiplat_platform.sqlite3}"
mkdir -p "$(dirname "$AIPLAT_PLATFORM_DB_PATH")"
echo "Platform DB: $AIPLAT_PLATFORM_DB_PATH"
PYTHONPATH="$PROJECT_ROOT/aiPlat-platform" nohup "$PY" -m uvicorn api.rest.routes:app --host 0.0.0.0 --port 8003 > /tmp/aiplat-platform.log 2>&1 &
PLATFORM_PID=$!
echo "PID: $PLATFORM_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8003/health >/dev/null 2>&1 && echo "✓ aiPlat-platform 启动成功 (8003)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 4: aiPlat-app =====
echo ""
echo "============================================================"
echo "  Step 4/6: 启动 aiPlat-app (端口 8004)"
echo "============================================================"

cd "$PROJECT_ROOT/aiPlat-app"
export AIPLAT_APP_DB_PATH="${AIPLAT_APP_DB_PATH:-$PROJECT_ROOT/aiPlat-app/data/aiplat_app.sqlite3}"
mkdir -p "$(dirname "$AIPLAT_APP_DB_PATH")"
echo "App DB: $AIPLAT_APP_DB_PATH"
PYTHONPATH="$PROJECT_ROOT/aiPlat-app" nohup "$PY" -m uvicorn api.rest.routes:app --host 0.0.0.0 --port 8004 > /tmp/aiplat-app.log 2>&1 &
APP_PID=$!
echo "PID: $APP_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8004/health >/dev/null 2>&1 && echo "✓ aiPlat-app 启动成功 (8004)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 5: aiPlat-management =====
echo ""
echo "============================================================"
echo "  Step 5/6: 启动 aiPlat-management (端口 8000)"
echo "============================================================"

cd "$PROJECT_ROOT/aiPlat-management"
nohup "$PY" -m uvicorn management.server:create_app --host 0.0.0.0 --port 8000 --factory > /tmp/aiplat-management.log 2>&1 &
MGMT_PID=$!
echo "PID: $MGMT_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8000/api/dashboard/status >/dev/null 2>&1 && echo "✓ aiPlat-management 启动成功 (8000)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 6: Frontend =====
echo ""
echo "============================================================"
echo "  Step 6/6: 启动前端 (端口 5173)"
echo "============================================================"

cd "$PROJECT_ROOT/aiPlat-management/frontend"

# Build if dist doesn't exist
if [ ! -d "dist" ]; then
    echo "正在构建前端..."
    npx vite build 2>&1 | tail -3
fi

nohup "$PY" "$PROJECT_ROOT/aiPlat-management/frontend/proxy_server.py" > /tmp/aiplat-frontend.log 2>&1 &
FRONTEND_PID=$!
echo "PID: $FRONTEND_PID"

sleep 2
for i in 1 2 3 4 5; do
    curl -s http://localhost:5173/ >/dev/null 2>&1 && echo "✓ 前端启动成功 (5173)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# 保存 PID
echo -e "$CORE_PID\n$INFRA_PID\n$PLATFORM_PID\n$APP_PID\n$MGMT_PID\n$FRONTEND_PID" > /tmp/aiplat.pids

echo ""
echo "============================================================"
echo "  ✓ 启动完成"
echo "============================================================"
echo ""
echo "服务:"
echo "  - core:        http://localhost:8002"
echo "  - infra:       http://localhost:8001"
echo "  - platform:    http://localhost:8003"
echo "  - app:         http://localhost:8004"
echo "  - management:  http://localhost:8000"
echo "  - 前端:        http://localhost:5173"
echo ""
echo "停止: ./stop.sh"
