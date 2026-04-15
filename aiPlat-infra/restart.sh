#!/bin/bash

# aiPlat-infra 重启脚本

echo "============================================================"
echo "  aiPlat-infra - 重启服务"
echo "============================================================"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 停止服务
echo "步骤 1/2: 停止服务"
"$SCRIPT_DIR/stop.sh"

echo ""

# 启动服务
echo "步骤 2/2: 启动服务"
"$SCRIPT_DIR/start.sh"