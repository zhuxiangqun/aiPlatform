#!/bin/bash
# install-offline.sh — aiPlat 客户现场离线安装脚本
#
# 用法: bash install.sh
# 前置: 客户机器已安装 Docker + Docker Compose + Ollama（或使用内嵌安装）
set -e

echo "============================================"
echo "  aiPlat 离线部署 — 客户现场安装"
echo "============================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ═══════════════════════════════════════════════════════════
# Step 0: Check prerequisites
# ═══════════════════════════════════════════════════════════
echo ""
echo "[0/4] 检查运行环境..."

# Docker
if ! command -v docker &>/dev/null; then
    echo "  ❌ Docker 未安装。请先安装 Docker: https://docs.docker.com/engine/install/"
    exit 1
fi
echo "  ✓ Docker: $(docker --version | head -1)"

# Docker Compose
if ! docker compose version &>/dev/null; then
    echo "  ❌ Docker Compose 未安装"
    exit 1
fi
echo "  ✓ Docker Compose: $(docker compose version --short 2>/dev/null || echo 'OK')"

# Ollama (optional — warn if missing)
if ! command -v ollama &>/dev/null; then
    echo "  ⚠ Ollama 未安装 — 模型将跳过，仅部署管理平台"
    HAS_OLLAMA=false
else
    echo "  ✓ Ollama: $(ollama --version 2>/dev/null || echo 'OK')"
    HAS_OLLAMA=true
fi

# ═══════════════════════════════════════════════════════════
# Step 1: Load Docker images
# ═══════════════════════════════════════════════════════════
echo ""
echo "[1/4] 加载 Docker 镜像..."
if [ -d "images" ] && ls images/*.tar 1>/dev/null 2>&1; then
    for img in images/*.tar; do
        echo "  加载: $(basename "$img")"
        docker load -i "$img"
    done
    echo "  ✓ 所有镜像加载完成"
else
    echo "  ⚠ 未找到镜像文件 (images/*.tar)，跳过"
fi

# ═══════════════════════════════════════════════════════════
# Step 2: Configure environment
# ═══════════════════════════════════════════════════════════
echo ""
echo "[2/4] 配置环境变量..."
if [ -f "config/.env.example" ]; then
    cp config/.env.example config/.env
    echo "  ✓ 已从模板创建 config/.env"
    echo "  ⚠ 请编辑 config/.env 填入必要的 API Key 和配置项"
else
    echo "  ⚠ config/.env.example 未找到，跳过"
fi

# ═══════════════════════════════════════════════════════════
# Step 3: Pull models (optional)
# ═══════════════════════════════════════════════════════════
echo ""
echo "[3/4] 拉取模型..."
if [ "$HAS_OLLAMA" = "true" ]; then
    # Start Ollama if not running
    ollama list &>/dev/null || ollama serve &
    sleep 2

    if [ -f "models_manifest.json" ]; then
        echo "  从 models_manifest.json 读取模型列表..."
        # Use python to parse JSON if available, otherwise use grep
        if command -v python3 &>/dev/null; then
            python3 -c "
import json
with open('models_manifest.json') as f:
    data = json.load(f)
for m in data.get('local', []):
    print(f'  拉取: {m[\"name\"]}')
" | while read -r line; do
                echo "$line"
            done
            python3 -c "
import json, subprocess, sys
with open('models_manifest.json') as f:
    data = json.load(f)
for m in data.get('local', []):
    name = m['name']
    print(f'  ollama pull {name}...')
    subprocess.run(['ollama', 'pull', name], timeout=300)
" 2>/dev/null || echo "  ⚠ 模型拉取失败，请手动执行 ollama pull"
        else
            echo "  ⚠ Python3 未安装，请手动执行 ollama pull <model_name>"
        fi
    elif [ -f "deploy.sh" ]; then
        bash deploy.sh 2>/dev/null || echo "  ⚠ deploy.sh 执行失败"
    else
        echo "  ⚠ 未找到模型清单，跳过"
    fi
else
    echo "  ⚠ 跳过（Ollama 未安装）"
fi

# ═══════════════════════════════════════════════════════════
# Step 4: Start services
# ═══════════════════════════════════════════════════════════
echo ""
echo "[4/4] 启动服务..."
if [ -f "config/docker-compose.yml" ]; then
    cd config
    docker compose up -d
    echo ""
    echo "============================================"
    echo "  ✓ aiPlat 部署完成"
    echo "  管理端: http://localhost:5173"
    echo "  API:    http://localhost:8000"
    echo "============================================"
else
    echo "  ❌ config/docker-compose.yml 未找到，部署失败"
    exit 1
fi
