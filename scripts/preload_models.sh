#!/bin/bash
# preload_models.sh — 预先下载所有需要的模型到本地缓存
# 使用 HF 镜像加速（国内访问 huggingface.co 很慢）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
VENV_PY="$SCRIPT_DIR/.venv/bin/python"

echo "============================================================"
echo "  aiPlat — 预加载模型"
echo "============================================================"
echo ""

# Load env
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a; source "$SCRIPT_DIR/.env"; set +a
fi

HF_MIRROR="${HF_ENDPOINT:-https://hf-mirror.com}"
echo "HF Mirror: $HF_MIRROR"

# ── Models to preload ──
# Format: "repo_id" "description"
MODELS=(
  "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" "多语言嵌入模型 (118MB, core fallback)"
  "sentence-transformers/all-MiniLM-L6-v2" "轻量英文嵌入模型 (80MB, 工具选择器回退)"
  "jinaai/jina-embeddings-v2-base-zh" "中文嵌入模型 (平台服务, ~500MB)"
  "jinaai/jina-reranker-v2-base-multilingual" "多语言重排序模型 (548MB)"
)
# Ollama 模型需单独下载:
#   ollama pull minicpm-v:8b  (VLM)
#   ollama pull gemma4:12b    (LLM)
#   (如未安装 qwen2.5-coder:7b, 也需 ollama pull)

download_model() {
  local repo="$1"
  local desc="$2"
  local short_name=$(echo "$repo" | sed 's|.*/||')
  
echo ""
echo "提示: 如果网络不可达，系统会自动使用 hash embedding 后端。"
echo "  hash 后端不需要任何模型，0 下载，0 网络依赖。"
echo "  设置 AIPLAT_EMBED_BACKEND=hash 即可启用（start.sh 已默认设置）。"
  echo "━━━ $short_name ━━━"
  echo "  说明: $desc"
  echo "  存储: ~/.cache/huggingface/hub/"
  
  # Check if already cached with weight files and NO .no_exist errors
  local short_name=$(echo "$repo" | sed 's|.*/||')
  local cached=0
  local has_no_exist=0
  
  # Check for .no_exist markers (download failures)
  for d in ~/.cache/huggingface/hub/models--*/snapshots/ ~/.cache/torch/sentence_transformers/; do
    local model_dir=$(find "$d" -maxdepth 1 -name "*${short_name}*" -type d 2>/dev/null | head -1)
    if [ -n "$model_dir" ]; then
      local no_exist_count=$(find "$model_dir" -path "*/.no_exist/*" -type f 2>/dev/null | wc -l)
      if [ "$no_exist_count" -gt 0 ]; then
        has_no_exist=1
        echo "  ⚠️ 发现 $no_exist_count 个下载失败标记，需要重新下载"
        break
      fi
    fi
  done
  
  if [ "$has_no_exist" -eq 1 ]; then
    echo "  正在强制重新下载..."
    # Force re-download
    "$VENV_PY" -c "
import os
os.environ['HF_ENDPOINT'] = '$HF_MIRROR'
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
from huggingface_hub import snapshot_download
print(f'  正在下载 {repo}...')
path = snapshot_download('$repo', resume_download=True, max_workers=4)
print(f'  ✅ 下载完成: {path}')
" 2>&1 | tail -3
    if [ $? -eq 0 ]; then
      echo "  ✅ $short_name 就绪"
    else
      echo "  ❌ $short_name 下载失败"
    fi
    return
  fi
  
  # Check if weight files exist
  for d in ~/.cache/huggingface/hub/models--*/snapshots/*/ ~/.cache/torch/sentence_transformers/models--*--${short_name}/; do
    if [ -d "$d" ] 2>/dev/null; then
      local weight_count=$(find "$d" -name "*.safetensors" -o -name "*.bin" -o -name "*.model" -o -name "*.msgpack" 2>/dev/null | grep -v ".no_exist" | wc -l)
      if [ "$weight_count" -gt 0 ]; then
        cached=1
        break
      fi
    fi
  done
  
  if [ "$cached" -eq 1 ]; then
    echo "  ✅ 已缓存 (跳过)"
    return 0
  fi
  
  echo "  ⏳ 下载中..."
  
  "$VENV_PY" -c "
import os, sys
os.environ['HF_ENDPOINT'] = '$HF_MIRROR'
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
from sentence_transformers import SentenceTransformer
print(f'  正在加载 {repo}...')
model = SentenceTransformer('$repo')
print(f'  ✅ 下载完成: {model.get_sentence_embedding_dimension()} 维')
" 2>&1 | tail -3
  
  if [ $? -eq 0 ]; then
    echo "  ✅ $short_name 就绪"
  else
    echo "  ❌ $short_name 下载失败 (可能网络问题，稍后重试)"
  fi
}

# ── Main ──
echo ""
echo "需要下载 ${#MODELS[@]} 个模型，总计约 750MB"

for ((i=0; i<${#MODELS[@]}; i+=2)); do
  repo="${MODELS[i]}"
  desc="${MODELS[i+1]}"
  download_model "$repo" "$desc"
done

echo ""
echo "============================================================"
echo "  ✅ 模型预加载完成"
echo "============================================================"
echo ""
echo "如果全部成功，可以设置环境变量让服务只使用本地模型："
echo "  export HF_HUB_OFFLINE=1"
echo "  export TRANSFORMERS_OFFLINE=1"
echo "  export HF_DATASETS_OFFLINE=1"
echo ""
echo "这些环境变量已在 start.sh 中默认设置。"
