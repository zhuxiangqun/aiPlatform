#!/usr/bin/env bash
# install-offline.sh — aiPlat 客户侧离线部署 (FDE Toolkit A)
#
# 被打包进 aiplat-offline-*.tar.gz 中。
# 客户现场运行: ./install.sh
#
# 步骤: Docker load → Ollama create → .env 配置 → docker-compose up → health check
set -euo pipefail

MODE="${1:-airgap}"
echo "=== aiPlat Offline Installer (mode=$MODE) ==="

# ═══════════════════════════════════════════════════════════
# 1. 加载 Docker 镜像
# ═══════════════════════════════════════════════════════════
for img in images/*.tar; do
    [ -f "$img" ] || continue
    docker load -i "$img"
    echo "  ✓ loaded: $img"
done

# ═══════════════════════════════════════════════════════════
# 2. 恢复本地模型 (Ollama create)
# ═══════════════════════════════════════════════════════════
if ls models/*.gguf 1>/dev/null 2>&1; then
    for gguf in models/*.gguf; do
        [ -f "$gguf" ] || continue
        model_name=$(basename "$gguf" .gguf)
        ollama create "$model_name" -f "$gguf" && echo "  ✓ model: $model_name" || echo "  ⚠ failed: $model_name"
    done
fi

# ═══════════════════════════════════════════════════════════
# 3. 提示远程模型 API keys (models.yaml 已在打包时生成)
# ═══════════════════════════════════════════════════════════
if [ -f config/models.yaml ]; then
    python3 -c "
import json, os
try:
    import yaml
    data = yaml.safe_load(open('config/models.yaml'))
except Exception:
    data = json.load(open('config/models.yaml'))
for m in data.get('remote', []):
    key = input(f'  API key for {m[\"name\"]} ({m[\"provider\"]}) [回车跳过]: ')
    if key.strip():
        print(f'{m.get(\"env_var\",\"\")}={key.strip()}')
" > .env.local 2>/dev/null || true
fi

# ═══════════════════════════════════════════════════════════
# 4. 启动服务
# ═══════════════════════════════════════════════════════════
if [ -f config/docker-compose.yml ]; then
    docker compose -f config/docker-compose.yml up -d
else
    docker compose up -d
fi

echo ""
echo "=== 等待健康检查… ==="
for i in $(seq 1 30); do
    curl -sf http://localhost:8002/api/core/health && break
    sleep 2
done

echo ""
echo "✅ aiPlat 已就绪, 访问 http://localhost:8002"
