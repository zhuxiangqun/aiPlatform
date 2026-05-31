#!/bin/bash
# aiPlat 用户一键部署脚本
# 用法: bash run.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "  aiPlat 一键部署"
echo "============================================"

if ! command -v docker &> /dev/null; then
    echo "❌ 未检测到 Docker，请先安装 Docker Engine 20.10+"
    exit 1
fi

echo "[1/3] 加载镜像..."
docker load -q < "$SCRIPT_DIR/images/aiplat-core.tar"
docker load -q < "$SCRIPT_DIR/images/aiplat-management.tar"
docker load -q < "$SCRIPT_DIR/images/aiplat-frontend.tar"

echo "[2/3] 检查配置..."
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "⚠  未找到 .env 配置文件，使用默认配置"
fi

echo "[3/3] 启动服务..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo ""
echo "============================================"
echo "  ✅ 部署完成"
echo "  访问地址: http://localhost:5173"
echo "  默认账号: admin / admin"
echo "  停止服务: docker compose -f $SCRIPT_DIR/docker-compose.yml down"
echo "  数据目录: $SCRIPT_DIR/data/"
echo "============================================"
