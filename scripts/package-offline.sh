#!/usr/bin/env bash
# package-offline.sh — aiPlat 离线部署包打包 (FDE Toolkit A)
#
# 被 fde.py 的 _bg_package() 或 FDE 手动调用。
# 输入: BUILD_DIR (环境变量, fde.py 设置)
# 输出: ${BUILD_DIR}.tar.gz
#
# 与 ModelManager.export_models() 协作 — 模型发现/分流由 Python 侧完成,
# 本脚本负责 Docker 镜像构建+导出 + 配置拷贝 + tar 打包。
set -euo pipefail

BUILD_DIR="${BUILD_DIR:-/tmp/aiplat-offline-default}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== aiPlat Offline Package Builder ==="
echo "  build dir: $BUILD_DIR"
echo "  repo: $REPO"

# ═══════════════════════════════════════════════════════════
# 1. Build Docker images
# ═══════════════════════════════════════════════════════════
echo ""
echo "--- Building Docker images ---"
cd "$REPO"
docker compose build infra core platform app management frontend 2>&1 | tail -5 || {
    echo "  ⚠ docker compose build 失败 — 尝试使用已存在的镜像"
}

# ═══════════════════════════════════════════════════════════
# 2. Tag + Export Docker images
# ═══════════════════════════════════════════════════════════
echo ""
echo "--- Exporting Docker images ---"
mkdir -p "$BUILD_DIR/images"

# Map: compose service name → export image name
declare -A svc_map=(
    ["infra"]="aiplat-infra"
    ["core"]="aiplat-core"
    ["platform"]="aiplat-platform"
    ["app"]="aiplat-app"
    ["management"]="aiplat-management"
    ["frontend"]="aiplat-frontend"
)

for compose_svc in "${!svc_map[@]}"; do
    export_name="${svc_map[$compose_svc]}"
    # Try compose project name first, then fall back to simple name
    compose_img="aiplatform-${compose_svc}"
    if docker image inspect "${compose_img}:latest" &>/dev/null; then
        docker tag "${compose_img}:latest" "${export_name}:latest" 2>/dev/null || true
    fi
    if docker image inspect "${export_name}:latest" &>/dev/null; then
        docker save "${export_name}:latest" -o "$BUILD_DIR/images/${export_name}.tar"
        echo "  ✓ exported: ${export_name}.tar"
    else
        echo "  ⚠ skip: ${export_name}:latest not found (run 'docker compose build ${compose_svc}' first)"
    fi
done

# ═══════════════════════════════════════════════════════════
# 3. Copy configuration files
# ═══════════════════════════════════════════════════════════
echo ""
echo "--- Copying configs ---"
mkdir -p "$BUILD_DIR/config"
cp "$REPO/docker-compose.yml" "$BUILD_DIR/config/" 2>/dev/null || echo "  ⚠ docker-compose.yml not found"
cp "$REPO/.env.example" "$BUILD_DIR/config/" 2>/dev/null || echo "  ⚠ .env.example not found"
cp "$REPO/.env.example" "$BUILD_DIR/config/.env" 2>/dev/null || true

# ═══════════════════════════════════════════════════════════
# 4. Copy install script
# ═══════════════════════════════════════════════════════════
echo ""
echo "--- Copying install script ---"
cp "$REPO/scripts/install-offline.sh" "$BUILD_DIR/install.sh" 2>/dev/null && chmod +x "$BUILD_DIR/install.sh" || {
    echo "  ⚠ install-offline.sh not found — generating minimal install script"
    cat > "$BUILD_DIR/install.sh" << 'INSTALL_EOF'
#!/bin/bash
set -e
echo "=== aiPlat Offline Installer ==="
cd "$(dirname "$0")"

# Load Docker images
echo "--- Loading Docker images ---"
for img in images/*.tar; do
    [ -f "$img" ] && docker load -i "$img" && echo "  ✓ loaded: $img"
done

# Pull models
echo "--- Pulling Ollama models ---"
bash deploy.sh 2>/dev/null || echo "  ⚠ deploy.sh not found, skip model pull"

# Start services
echo "--- Starting services ---"
cp config/.env.example config/.env 2>/dev/null || true
docker compose -f config/docker-compose.yml --env-file config/.env up -d
echo "  ✓ aiPlat launched at http://localhost:5173"
echo "  Management API: http://localhost:8000"
INSTALL_EOF
    chmod +x "$BUILD_DIR/install.sh"
}

# ═══════════════════════════════════════════════════════════
# 5. Tar packaging
# ═══════════════════════════════════════════════════════════
echo ""
echo "--- Packaging ---"
ARCHIVE="${BUILD_DIR}.tar.gz"
tar -czf "$ARCHIVE" -C "$(dirname "$BUILD_DIR")" "$(basename "$BUILD_DIR")"
echo "  ✓ package: $ARCHIVE"
echo "  size: $(du -sh "$ARCHIVE" | cut -f1)"
echo ""
echo "=== Package complete ==="
