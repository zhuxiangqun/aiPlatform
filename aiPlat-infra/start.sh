#!/bin/bash

# aiPlat-infra 启动脚本

echo "============================================================"
echo "  aiPlat-infra - 基础设施层 API 服务"
echo "============================================================"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# 安装依赖
echo "正在安装依赖..."
cd "$SCRIPT_DIR"
pip install -e .[dev] 2>&1 | grep -E "(Successfully|ERROR|error)" || {
    echo "警告: 依赖安装可能有问题，继续..."
}

echo ""
echo "依赖安装完成！"
echo ""

# 启动服务
echo "启动 aiPlat-infra API 服务..."
echo ""

PORT=${PORT:-8001}

nohup python3 -m infra.management.api.run_server --host 0.0.0.0 --port $PORT > /tmp/aiplat-infra.log 2>&1 &
PID=$!

echo "服务 PID: $PID"

# 等待启动
sleep 3

# 检查是否启动成功
if ! kill -0 $PID 2>/dev/null; then
    echo "错误: 服务启动失败"
    cat /tmp/aiplat-infra.log
    exit 1
fi

echo "服务已启动: http://localhost:$PORT"
echo "API 文档: http://localhost:$PORT/docs"
echo ""

# 保存 PID
echo "$PID" > /tmp/aiplat-infra.pid

echo "============================================================"
echo "  ✓ aiPlat-infra 启动完成"
echo "============================================================"
echo ""
echo "服务地址:"
echo "  - API:      http://localhost:$PORT"
echo "  - 健康检查: http://localhost:$PORT/health"
echo "  - API 文档: http://localhost:$PORT/docs"
echo ""
echo "查看日志: tail -f /tmp/aiplat-infra.log"
echo "停止服务: kill $PID 或 ./stop.sh"