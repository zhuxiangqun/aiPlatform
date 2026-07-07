#!/usr/bin/env bash
# package-offline.sh — aiPlat 离线部署包打包 (FDE Toolkit A)
#
# 被 fde.py 的 _bg_package() 或 FDE 手动调用。
# 输入: BUILD_DIR (环境变量, fde.py 设置)
# 输出: ${BUILD_DIR}.tar.gz
#
# 与 ModelManager.export_models() 协作 — 模型发现/分流由 Python 侧完成,
# 本脚本只负责 Docker 镜像导出 + 配置拷贝 + tar 打包。
set -euo pipefail

BUILD_DIR="${BUILD_DIR:-/tmp/aiplat-offline-default}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== aiPlat Offline Package Builder ==="
echo "  build dir: $BUILD_DIR"

# ═══════════════════════════════════════════════════════════
# 1. Docker 镜像导出
# ═══════════════════════════════════════════════════════════
mkdir -p "$BUILD_DIR/images"
imgs=(core management frontend)
for svc in "${imgs[@]}"; do
    if docker image inspect "aiplat-${svc}:latest" &>/dev/null; then
        docker save "aiplat-${svc}:latest" -o "$BUILD_DIR/images/aiplat-${svc}.tar"
        echo "  ✓ docker save: aiplat-${svc}"
    else
        echo "  ⚠ skip: aiplat-${svc}:latest not found"
    fi
done

# ═══════════════════════════════════════════════════════════
# 2. 拷贝配置
# ═══════════════════════════════════════════════════════════
mkdir -p "$BUILD_DIR/config"
cp "$REPO/docker-compose.yml" "$BUILD_DIR/config/" 2>/dev/null || true
cp "$REPO/.env.example" "$BUILD_DIR/config/" 2>/dev/null || true

# ═══════════════════════════════════════════════════════════
# 3. 拷贝 install 脚本 (install-offline.sh)
# ═══════════════════════════════════════════════════════════
cp "$REPO/scripts/install-offline.sh" "$BUILD_DIR/install.sh" 2>/dev/null || {
    echo "  ⚠ install-offline.sh 未找到 — 跳过"
}

# ═══════════════════════════════════════════════════════════
# 4. tar 打包
# ═══════════════════════════════════════════════════════════
ARCHIVE="${BUILD_DIR}.tar.gz"
tar -czf "$ARCHIVE" -C "$(dirname "$BUILD_DIR")" "$(basename "$BUILD_DIR")"
echo "  ✓ package: $ARCHIVE"
echo "  size: $(du -sh "$ARCHIVE" | cut -f1)"
