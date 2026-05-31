#!/bin/bash
# aiPlat 构建并打包发布脚本
# 用法: bash scripts/build-release.sh [ids]
#   ids: 可选，格式 "agent:xxx,skill:yyy"
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

IDS="${1:-}"
KIT_DIR="$SCRIPT_DIR/deploy-kit"
rm -rf "$KIT_DIR"
mkdir -p "$KIT_DIR/images"

echo "[build] $(date '+%H:%M:%S') 开始构建..."

# 1. 导出 workspace 配置为种子文件（首次启动自动加载）
echo "[build] $(date '+%H:%M:%S') 导出 workspace 配置..."
if [ -n "$IDS" ]; then
    python3 "$SCRIPT_DIR/scripts/export_workspace.py" --ids "$IDS" 2>/dev/null || echo "[build] (workspace 导出跳过)"
else
    python3 "$SCRIPT_DIR/scripts/export_workspace.py" 2>/dev/null || echo "[build] (workspace 导出跳过)"
fi

# 2. 构建前端
echo "[build] $(date '+%H:%M:%S') 构建前端..."
cd "$SCRIPT_DIR/aiPlat-management/frontend"
npm run build 2>&1
cd "$SCRIPT_DIR"

# 3. Docker 构建
echo "[build] $(date '+%H:%M:%S') docker build aiplat-core..."
docker build -t aiplat-core:latest -f "$SCRIPT_DIR/Dockerfile.core" "$SCRIPT_DIR"

echo "[build] $(date '+%H:%M:%S') docker build aiplat-management..."
docker build -t aiplat-management:latest -f "$SCRIPT_DIR/Dockerfile.management" "$SCRIPT_DIR"

echo "[build] $(date '+%H:%M:%S') docker build aiplat-frontend..."
docker build -t aiplat-frontend:latest -f "$SCRIPT_DIR/Dockerfile.frontend" "$SCRIPT_DIR/aiPlat-management/frontend"

# 4. docker save → tar
echo "[build] $(date '+%H:%M:%S') 导出镜像..."
docker save aiplat-core:latest -o "$KIT_DIR/images/aiplat-core.tar"
docker save aiplat-management:latest -o "$KIT_DIR/images/aiplat-management.tar"
docker save aiplat-frontend:latest -o "$KIT_DIR/images/aiplat-frontend.tar"

# 5. 复制部署文件
cp "$SCRIPT_DIR/docker-compose.yml" "$KIT_DIR/"
cp "$SCRIPT_DIR/run.sh" "$KIT_DIR/"
cp "$SCRIPT_DIR/.env.example" "$KIT_DIR/.env" 2>/dev/null || echo "# aiPlat 环境配置" > "$KIT_DIR/.env"
cp "$SCRIPT_DIR/README.md" "$KIT_DIR/" 2>/dev/null || echo "# aiPlat 部署手册" > "$KIT_DIR/README.md"

# 6. 打包 zip
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ZIP_NAME="deploy-kit-${TIMESTAMP}.zip"
cd "$KIT_DIR" && zip -q -r "../$ZIP_NAME" .
cd "$SCRIPT_DIR"

FILE_SIZE=$(ls -lh "$ZIP_NAME" | awk '{print $5}')
echo "[build] $(date '+%H:%M:%S') ✓ 构建完成: $ZIP_NAME ($FILE_SIZE)"
echo "$ZIP_NAME"
