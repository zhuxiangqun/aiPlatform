#!/bin/bash

# aiPlat-management 启动脚本
# 需要先启动 aiPlat-infra 层，再启动 aiPlat-management 层

echo "============================================================"
echo "  aiPlat-platform - 启动服务"
echo "============================================================"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
    echo "错误: 需要 Python 3.10 或更高版本"
    echo "当前版本: $PYTHON_VERSION"
    exit 1
fi

echo "Python 版本: $PYTHON_VERSION"
echo ""

# ===== Step 1: 启动 aiPlat-infra 层 =====
echo "============================================================"
echo "  Step 1/2: 启动 aiPlat-infra (基础设施层)"
echo "============================================================"
echo ""

echo "正在安装 aiPlat-infra 依赖..."
cd "$PROJECT_ROOT/aiPlat-infra"
pip install -e . 2>&1 | grep -E "(Successfully|ERROR|error)" || {
    echo "警告: aiPlat-infra 安装可能有问题，继续..."
}

echo ""
echo "启动 aiPlat-infra API 服务 (端口 8001)..."
nohup python3 -m infra.management.api.run_server --host 0.0.0.0 --port 8001 > /tmp/aiplat-infra.log 2>&1 &
INFRA_PID=$!
echo "aiPlat-infra PID: $INFRA_PID"

# 等待 infra 启动
echo "等待 aiPlat-infra 启动..."
sleep 3

# 检查 infra 是否启动成功
if ! kill -0 $INFRA_PID 2>/dev/null; then
    echo "错误: aiPlat-infra 启动失败"
    cat /tmp/aiplat-infra.log
    exit 1
fi

# 检查 infra API 是否可用
for i in {1..10}; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "aiPlat-infra 已启动: http://localhost:8001"
        break
    fi
    echo "等待 aiPlat-infra 就绪... ($i/10)"
    sleep 1
done

# ===== Step 2: 启动 aiPlat-management 层 =====
echo ""
echo "============================================================"
echo "  Step 2/2: 启动 aiPlat-management (管理系统层)"
echo "============================================================"
echo ""

echo "正在安装 aiPlat-management 依赖..."
cd "$SCRIPT_DIR"
pip install -e .[dev] 2>&1 | grep -E "(Successfully|ERROR|error)" || {
    echo "警告: aiPlat-management 安装可能有问题，继续..."
}

echo ""
echo "启动 aiPlat-management API 服务 (端口 8000)..."
nohup python3 -m uvicorn management.server:create_app --host 0.0.0.0 --port 8000 --factory > /tmp/aiplat-management.log 2>&1 &
MGMT_PID=$!
echo "aiPlat-management PID: $MGMT_PID"

# 等待 management 启动
echo "等待 aiPlat-management 启动..."
sleep 3

# 检查 management 是否启动成功
if ! kill -0 $MGMT_PID 2>/dev/null; then
    echo "错误: aiPlat-management 启动失败"
    cat /tmp/aiplat-management.log
    # 停止 infra
    kill $INFRA_PID 2>/dev/null
    exit 1
fi

# 检查 management API 是否可用
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "aiPlat-management 已启动: http://localhost:8000"
        break
    fi
    echo "等待 aiPlat-management 就绪... ($i/10)"
    sleep 1
done

# 保存 PID 到文件
echo "$INFRA_PID" > /tmp/aiplat-infra.pid
echo "$MGMT_PID" > /tmp/aiplat-management.pid

# ===== Step 3: 启动前端 =====
echo ""
echo "============================================================"
echo "  服务状态"
echo "============================================================"
echo ""

# 检查前端目录是否存在
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    echo "启动前端开发服务器..."
    cd frontend
    nohup npm run dev > /tmp/aiplat-frontend.log 2>&1 &
    FRONTEND_PID=$!
    cd ..
    
    echo "前端 PID: $FRONTEND_PID"
    echo "$FRONTEND_PID" >> /tmp/aiplat-management.pid
    
    echo ""
    echo "============================================================"
    echo "  ✓ 所有服务启动完成"
    echo "============================================================"
    echo ""
    echo "服务地址:"
    echo "  - aiPlat-infra:      http://localhost:8001"
    echo "  - aiPlat-management: http://localhost:8000"
    echo "  - Frontend:          http://localhost:5173"
    echo ""
    echo "查看日志:"
    echo "  - infra日志:      tail -f /tmp/aiplat-infra.log"
    echo "  - management日志: tail -f /tmp/aiplat-management.log"
    echo "  - frontend日志:   tail -f /tmp/aiplat-frontend.log"
    echo ""
    echo "停止服务: ./stop.sh"
else
    echo "============================================================"
    echo "  ✓ 后端服务启动完成"
    echo "============================================================"
    echo ""
    echo "服务地址:"
    echo "  - aiPlat-infra:      http://localhost:8001"
    echo "  - aiPlat-management: http://localhost:8000"
    echo ""
    echo "查看日志:"
    echo "  - infra日志:      tail -f /tmp/aiplat-infra.log"
    echo "  - management日志: tail -f /tmp/aiplat-management.log"
    echo ""
    echo "停止服务: ./stop.sh"
fi