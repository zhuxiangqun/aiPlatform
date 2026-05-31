#!/bin/bash
# 一键部署：停止 → 拉代码 → 构建 → 启动

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[deploy] $(date '+%H:%M:%S') 停止服务..."
bash "$SCRIPT_DIR/stop.sh" > /dev/null 2>&1 || true

echo "[deploy] $(date '+%H:%M:%S') 拉取 aiPlat-core..."
cd "$SCRIPT_DIR/aiPlat-core" && git pull --ff-only 2>&1

echo "[deploy] $(date '+%H:%M:%S') 拉取 aiPlat-management..."
cd "$SCRIPT_DIR/aiPlat-management" && git pull --ff-only 2>&1

echo "[deploy] $(date '+%H:%M:%S') 构建前端..."
cd "$SCRIPT_DIR/aiPlat-management/frontend" && npm run build 2>&1

echo "[deploy] $(date '+%H:%M:%S') 启动服务..."
cd "$SCRIPT_DIR" && bash start.sh > /dev/null 2>&1 &

echo "[deploy] $(date '+%H:%M:%S') ✓ 部署完成"
