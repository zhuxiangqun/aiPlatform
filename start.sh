#!/bin/bash

# aiPlat-platform 三层 + platform/app + 前端 启动脚本
# 启动顺序:
#   aiPlat-core (8002) → aiPlat-infra (8001) → aiPlat-platform (8003) → aiPlat-app (8004) → aiPlat-management (8000) → frontend (5173)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

load_env_file () {
  local env_file="$1"
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi
}

# 项目根目录本地环境配置
load_env_file "$PROJECT_ROOT/.env"
load_env_file "$PROJECT_ROOT/.env.local"

VENV_DIR="$PROJECT_ROOT/.venv"
PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
# Some Python distributions (e.g. uv-managed) mark environments as externally managed (PEP 668),
# which makes pip refuse installs unless explicitly overridden.
PIP_FLAGS="--break-system-packages"
# Reduce noisy warnings like "script is installed in ... which is not on PATH".
export PIP_NO_WARN_SCRIPT_LOCATION=1

# Ensure venv console scripts (e.g., mineru) are discoverable for subprocess() calls.
export PATH="$VENV_DIR/bin:$PATH"

# 统一数据目录（KB/执行记录等），确保 core/platform/app 使用同一份持久化路径。
# 默认放在项目目录下，避免不同用户/不同启动方式导致写到不同的 ~/.aiplat。
export AIPLAT_HOME="${AIPLAT_HOME:-$PROJECT_ROOT/.aiplat}"

# 统一外部 LLM 默认走 DeepSeek。
# - 通用/对话/重写类默认使用 deepseek-chat
# - Agent/推理类默认使用 deepseek-reasoner
# - 若显式传入 AIPLAT_LLM_*，仍以显式配置为准
export AIPLAT_LLM_PROVIDER="${AIPLAT_LLM_PROVIDER:-deepseek}"
export AIPLAT_LLM_BASE_URL="${AIPLAT_LLM_BASE_URL:-${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}}"
export AIPLAT_LLM_API_KEY="${AIPLAT_LLM_API_KEY:-${DEEPSEEK_API_KEY:-}}"
export AIPLAT_LLM_MODEL="${AIPLAT_LLM_MODEL:-deepseek-chat}"
export AIPLAT_DOC_LLM_MODEL="${AIPLAT_DOC_LLM_MODEL:-${AIPLAT_LLM_MODEL}}"
export AIPLAT_AGENT_MODEL="${AIPLAT_AGENT_MODEL:-deepseek-reasoner}"
# Builder Pipeline: 单次流水线 token 预算（防止费用过高）
export AIPLAT_BUILDER_MAX_TOKENS="${AIPLAT_BUILDER_MAX_TOKENS:-50000}"
if [ -z "${AIPLAT_LLM_API_KEY:-}" ]; then
  echo "提示：未检测到 DeepSeek API Key。请先设置 DEEPSEEK_API_KEY 或 AIPLAT_LLM_API_KEY。"
fi

# Reduce native BLAS thread contention/crashes (notably with libpaddle on macOS)
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

# Dev: disable approval gates (avoid manual approve/replay loops during local MVP).
export AIPLAT_APPROVALS_DISABLED="${AIPLAT_APPROVALS_DISABLED:-1}"

# Infra: port→service mapping for network manager (was hardcoded, now env-driven).
# Format: "port=service:name,port=service:name,..."
export AIPLAT_PORT_SERVICES="${AIPLAT_PORT_SERVICES:-8002=core-api:aiPlat-core,8001=infra-api:aiPlat-infra,8000=management-api:aiPlat-management,8003=platform-api:aiPlat-platform,8004=app-api:aiPlat-app,5173=frontend-dev:frontend}"
# Infra: target processes for service manager monitoring.
# Format: "name:cmdline:port,name:cmdline:port,..."
export AIPLAT_TARGET_PROCESSES="${AIPLAT_TARGET_PROCESSES:-aiPlat-core:uvicorn:8002,aiPlat-infra:uvicorn:8001,aiPlat-platform:uvicorn:8003,aiPlat-app:uvicorn:8004,aiPlat-management:uvicorn:8000,frontend:proxy_server.py:5173}"

# Parser selection for KB ingest: auto|mineru|ocr
export AIPLAT_KB_PARSER="${AIPLAT_KB_PARSER:-auto}"

# MinerU tuning (defaults favor local CPU stability)
export AIPLAT_MINERU_BACKEND="${AIPLAT_MINERU_BACKEND:-pipeline}"
export AIPLAT_MINERU_LANG="${AIPLAT_MINERU_LANG:-ch}"
# First run may download models; allow longer timeout by default.
export AIPLAT_MINERU_TIMEOUT_SECONDS="${AIPLAT_MINERU_TIMEOUT_SECONDS:-1800}"
export AIPLAT_VIDEO_TRANSCRIBE_LANG="${AIPLAT_VIDEO_TRANSCRIBE_LANG:-auto}"
export AIPLAT_VIDEO_OCR_LANG="${AIPLAT_VIDEO_OCR_LANG:-eng+chi_sim}"

# Tesseract language data path (macOS Homebrew defaults). Needed for chi_sim OCR.
if [ -z "${TESSDATA_PREFIX:-}" ]; then
  if [ -d "/opt/homebrew/share/tessdata" ]; then
    export TESSDATA_PREFIX="/opt/homebrew/share/tessdata"
  elif [ -d "/usr/local/share/tessdata" ]; then
    export TESSDATA_PREFIX="/usr/local/share/tessdata"
  fi
fi

ensure_venv () {
  # Recreate venv if python is missing/broken (common after moving project folders).
  if [ ! -x "$PY" ] || ! "$PY" -V >/dev/null 2>&1; then
    echo "未发现或无法执行 $PY，正在创建虚拟环境: $VENV_DIR"
    rm -rf "$VENV_DIR" 2>/dev/null || true
    pick_py () {
      # 1) user override (absolute path recommended)
      if [ -n "${AIPLAT_PYTHON:-}" ] && [ -x "${AIPLAT_PYTHON}" ]; then
        echo "${AIPLAT_PYTHON}"
        return 0
      fi
      # 2) prefer Python >= 3.10 in PATH
      for c in python3.12 python3.11 python3.10 python3; do
        if command -v "$c" >/dev/null 2>&1; then
          echo "$(command -v "$c")"
          return 0
        fi
      done
      # 3) fallback system python
      if [ -x "/usr/bin/python3" ]; then
        echo "/usr/bin/python3"
        return 0
      fi
      return 1
    }

    PY_BOOTSTRAP="$(pick_py || true)"
    if [ -z "$PY_BOOTSTRAP" ]; then
      echo "错误：找不到 python3，请先安装 Python >= 3.10"
      exit 1
    fi

    # Ensure version >= 3.10
    PY_VER="$("$PY_BOOTSTRAP" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "")"
    if [ -z "$PY_VER" ]; then
      echo "错误：无法获取 Python 版本：$PY_BOOTSTRAP"
      exit 1
    fi
    PY_MAJOR="${PY_VER%%.*}"
    PY_MINOR="${PY_VER##*.}"
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
      echo "错误：当前可用 Python 版本为 $PY_VER（$PY_BOOTSTRAP），但 aiplat-core 需要 Python >= 3.10"
      echo ""
      echo "解决方案（推荐其一）："
      echo "  1) Homebrew 安装 Python 3.11："
      echo "     brew install python@3.11"
      echo "     export AIPLAT_PYTHON=\"$(command -v python3.11 2>/dev/null || echo /opt/homebrew/bin/python3.11)\""
      echo "  2) 或者 pyenv 安装 3.11+ 后再运行本脚本"
      exit 1
    fi

    echo "使用 Python $PY_VER 创建 venv: $PY_BOOTSTRAP"
    "$PY_BOOTSTRAP" -m venv "$VENV_DIR"
  fi
  # Ensure pip exists in venv (some envs may be created without pip or pip may be broken/missing).
  if [ ! -x "$PIP" ]; then
    "$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi
  "$PY" -m pip -q install --upgrade pip $PIP_FLAGS --no-warn-script-location >/dev/null 2>&1 || true
}

ensure_deps () {
  # Avoid reinstall every time; create a marker file once finished.
  if [ -f "$VENV_DIR/.aiplat_bootstrapped" ] && [ "${AIPLAT_FORCE_PIP_INSTALL:-0}" != "1" ]; then
    return 0
  fi
  echo "正在安装/更新依赖（可设置 AIPLAT_FORCE_PIP_INSTALL=1 强制重装）..."
  # NOTE: do not silence output; missing deps should be visible in terminal/logs.
  "$PY" -m pip install $PIP_FLAGS --no-warn-script-location -e "$PROJECT_ROOT/aiPlat-core"
  "$PY" -m pip install $PIP_FLAGS --no-warn-script-location -e "$PROJECT_ROOT/aiPlat-infra"
  # aiPlat-platform / aiPlat-app currently run via PYTHONPATH (no packaging metadata)
  "$PY" -m pip install $PIP_FLAGS --no-warn-script-location -e "$PROJECT_ROOT/aiPlat-management[dev]"
  # platform upload endpoints require multipart parsing
  "$PY" -m pip install $PIP_FLAGS --no-warn-script-location python-multipart
  # OCR runtime deps (used by core/apps/multimodal_kb_poc/ocr.py when engine=tesseract)
  "$PY" -m pip install $PIP_FLAGS --no-warn-script-location pillow pytesseract
  # Optional: MinerU parser (structure-driven). Enable by default for better table extraction.
  # Set AIPLAT_ENABLE_MINERU=0 to skip.
  if [ "${AIPLAT_ENABLE_MINERU:-1}" = "1" ]; then
    "$PY" -m pip install $PIP_FLAGS --no-warn-script-location "mineru[core]"
  fi
  touch "$VENV_DIR/.aiplat_bootstrapped"
}

ensure_video_deps () {
  if [ "${AIPLAT_ENABLE_VIDEO_INGEST:-1}" != "1" ]; then
    return 0
  fi
  echo "检查视频解析依赖..."
  HAS_FASTER_WHISPER=$("$PY" - <<'PY'
import importlib.util
print("1" if importlib.util.find_spec("faster_whisper") else "0")
PY
)
  HAS_OPENAI_WHISPER=$("$PY" - <<'PY'
import importlib.util
print("1" if importlib.util.find_spec("whisper") else "0")
PY
)
  if [ "$HAS_FASTER_WHISPER" != "1" ] && [ "$HAS_OPENAI_WHISPER" != "1" ]; then
    echo "安装视频转写依赖: faster-whisper"
    "$PY" -m pip install $PIP_FLAGS --no-warn-script-location faster-whisper
  fi

  if [ "${AIPLAT_ENABLE_VIDEO_URL_PAGES:-1}" = "1" ]; then
    if ! "$PY" -m yt_dlp --version >/dev/null 2>&1; then
      echo "安装视频平台页面下载依赖: yt-dlp"
      "$PY" -m pip install $PIP_FLAGS --no-warn-script-location yt-dlp
    fi
  fi
}

kill_port_if_any () {
  port="$1"
  pid=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "端口 $port 已被占用，强制停止 PID=$pid"
    kill -9 $pid 2>/dev/null || true
    sleep 1
  fi
}

ensure_venv
ensure_deps
ensure_video_deps

# Ensure runtime data directories exist
mkdir -p "$AIPLAT_HOME/tools"   # Plugin tool discovery (P2-12)
mkdir -p "$AIPLAT_HOME/skills"  # Workspace skills
mkdir -p "$AIPLAT_HOME/agents"  # AGENT.md role definitions
mkdir -p "$AIPLAT_HOME/output"  # Pipeline deploy output
mkdir -p "$AIPLAT_HOME/artifacts"     # ArtifactRegistry 版本化制品
mkdir -p "$AIPLAT_HOME/task_skills"   # L3 TaskSkill 记忆持久化
mkdir -p "$AIPLAT_HOME/auto_pipelines" # 自动审批流水线配置
mkdir -p "$AIPLAT_HOME/hooks"         # 用户空间 Hook 脚本

echo "============================================================"
echo "  aiPlat-platform - 启动服务"
echo "============================================================"
echo ""
echo "Python: $($PY --version 2>&1)"
echo "Python Path: $PY"
echo ""

# ===== Step 0: MinerU API (optional) =====
if [ "${AIPLAT_ENABLE_MINERU_API:-0}" = "1" ]; then
  echo "============================================================"
  echo "  Step 0/6: 启动 mineru-api (端口 8010)"
  echo "============================================================"
  kill_port_if_any 8010
  nohup "$VENV_DIR/bin/mineru-api" --host 127.0.0.1 --port 8010 > /tmp/aiplat-mineru-api.log 2>&1 &
  MINERU_API_PID=$!
  echo "PID: $MINERU_API_PID"
  # Make core reuse this mineru-api by default in this mode.
  export AIPLAT_MINERU_API_URL="${AIPLAT_MINERU_API_URL:-http://127.0.0.1:8010}"
  sleep 2
  for i in 1 2 3 4 5; do
      curl -s http://127.0.0.1:8010/health >/dev/null 2>&1 && echo "✓ mineru-api 启动成功 (8010)" && break
      echo "等待... ($i/5)"
      sleep 1
  done
  echo ""
fi

# ===== Step 1: aiPlat-core =====
echo "============================================================"
echo "  Step 1/4: 启动 aiPlat-core (端口 8002)"
echo "============================================================"

kill_port_if_any 8002

cd "$PROJECT_ROOT/aiPlat-core/core"
# 确保 ExecutionStore DB 路径稳定（用于 learning_artifacts / approvals 等管理功能）
export AIPLAT_EXECUTION_DB_PATH="${AIPLAT_EXECUTION_DB_PATH:-$PROJECT_ROOT/aiPlat-core/core/data/aiplat_executions.sqlite3}"
mkdir -p "$(dirname "$AIPLAT_EXECUTION_DB_PATH")"
echo "Execution DB: $AIPLAT_EXECUTION_DB_PATH"
PYTHONPATH="$PROJECT_ROOT/aiPlat-core" nohup "$PY" -m uvicorn server:app --host 0.0.0.0 --port 8002 > /tmp/aiplat-core.log 2>&1 &
CORE_PID=$!
echo "PID: $CORE_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8002/api/core/health >/dev/null 2>&1 && echo "✓ aiPlat-core 启动成功 (8002)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 2: aiPlat-infra =====
echo ""
echo "============================================================"
echo "  Step 2/4: 启动 aiPlat-infra (端口 8001)"
echo "============================================================"

kill_port_if_any 8001

cd "$PROJECT_ROOT/aiPlat-infra"
PYTHONPATH="$PROJECT_ROOT/aiPlat-infra" nohup "$PY" -m uvicorn infra.management.api.main:create_app --host 0.0.0.0 --port 8001 --factory > /tmp/aiplat-infra.log 2>&1 &
INFRA_PID=$!
echo "PID: $INFRA_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8001/api/infra/health >/dev/null 2>&1 && echo "✓ aiPlat-infra 启动成功 (8001)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 3: aiPlat-platform =====
echo ""
echo "============================================================"
echo "  Step 3/6: 启动 aiPlat-platform (端口 8003)"
echo "============================================================"

kill_port_if_any 8003

cd "$PROJECT_ROOT/aiPlat-platform"
export AIPLAT_PLATFORM_DB_PATH="${AIPLAT_PLATFORM_DB_PATH:-$PROJECT_ROOT/aiPlat-platform/data/aiplat_platform.sqlite3}"
mkdir -p "$(dirname "$AIPLAT_PLATFORM_DB_PATH")"
echo "Platform DB: $AIPLAT_PLATFORM_DB_PATH"
# DEV: allow management UI to use any apl_* api key without provisioning (MVP convenience).
export AIPLAT_PLATFORM_DEV_ALLOW_ANY_API_KEY="${AIPLAT_PLATFORM_DEV_ALLOW_ANY_API_KEY:-1}"
# DEV: grant anonymous users kb:read/kb:write scopes for local development.
export AIPLAT_PLATFORM_DEV_MODE="${AIPLAT_PLATFORM_DEV_MODE:-true}"
PYTHONPATH="$PROJECT_ROOT/aiPlat-platform" nohup "$PY" -m uvicorn api.rest.routes:app --host 0.0.0.0 --port 8003 > /tmp/aiplat-platform.log 2>&1 &
PLATFORM_PID=$!
echo "PID: $PLATFORM_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8003/health >/dev/null 2>&1 && echo "✓ aiPlat-platform 启动成功 (8003)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 4: aiPlat-app =====
echo ""
echo "============================================================"
echo "  Step 4/6: 启动 aiPlat-app (端口 8004)"
echo "============================================================"

kill_port_if_any 8004

cd "$PROJECT_ROOT/aiPlat-app"
export AIPLAT_APP_DB_PATH="${AIPLAT_APP_DB_PATH:-$PROJECT_ROOT/aiPlat-app/data/aiplat_app.sqlite3}"
mkdir -p "$(dirname "$AIPLAT_APP_DB_PATH")"
echo "App DB: $AIPLAT_APP_DB_PATH"
PYTHONPATH="$PROJECT_ROOT/aiPlat-app" nohup "$PY" -m uvicorn api.rest.routes:app --host 0.0.0.0 --port 8004 > /tmp/aiplat-app.log 2>&1 &
APP_PID=$!
echo "PID: $APP_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8004/health >/dev/null 2>&1 && echo "✓ aiPlat-app 启动成功 (8004)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# Persist pids for stop.sh (best effort)
PIDS="$CORE_PID $INFRA_PID $PLATFORM_PID $APP_PID"
if [ -n "${MINERU_API_PID:-}" ]; then
  PIDS="$PIDS $MINERU_API_PID"
fi
echo "$PIDS" > /tmp/aiplat.pids

# ===== Step 5: aiPlat-management =====
echo ""
echo "============================================================"
echo "  Step 5/6: 启动 aiPlat-management (端口 8000)"
echo "============================================================"

kill_port_if_any 8000

cd "$PROJECT_ROOT/aiPlat-management"
nohup "$PY" -m uvicorn management.server:create_app --host 0.0.0.0 --port 8000 --factory > /tmp/aiplat-management.log 2>&1 &
MGMT_PID=$!
echo "PID: $MGMT_PID"

sleep 3
for i in 1 2 3 4 5; do
    curl -s http://localhost:8000/api/dashboard/status >/dev/null 2>&1 && echo "✓ aiPlat-management 启动成功 (8000)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# ===== Step 6: Frontend =====
echo ""
echo "============================================================"
echo "  Step 6/6: 启动前端 (端口 5173)"
echo "============================================================"

kill_port_if_any 5173

cd "$PROJECT_ROOT/aiPlat-management/frontend"

# Build if needed
NEED_BUILD=0
if [ ! -d "dist" ]; then
    NEED_BUILD=1
elif [ "${AIPLAT_FORCE_FRONTEND_BUILD:-0}" = "1" ]; then
    NEED_BUILD=1
else
    # Cross-platform mtime check via python (safe in "python -c", no heredoc).
    # We are already in aiPlat-management/frontend directory here.
    NEED_BUILD=$("$PY" -c 'from pathlib import Path
import sys
try:
  frontend = Path.cwd()
  dist_index = frontend / "dist" / "index.html"
  if not dist_index.exists():
    print(1); sys.exit(0)
  src_targets = [
    frontend / "package.json",
    frontend / "vite.config.ts",
    frontend / "proxy_server.py",
    frontend / "index.html",
  ]
  src_dir = frontend / "src"
  if src_dir.exists():
    for p in src_dir.rglob("*"):
      if p.is_file():
        src_targets.append(p)
  dist_m = dist_index.stat().st_mtime
  latest = 0.0
  for p in src_targets:
    if p.exists():
      latest = max(latest, p.stat().st_mtime)
  print(1 if latest > dist_m else 0)
except Exception:
  print(1)
')
fi

if [ "$NEED_BUILD" = "1" ]; then
    echo "正在构建前端...（可设置 AIPLAT_FORCE_FRONTEND_BUILD=0 跳过）"
    npm install >/dev/null 2>&1 || true
    npx vite build 2>&1 | tail -3
fi

nohup "$PY" "$PROJECT_ROOT/aiPlat-management/frontend/proxy_server.py" > /tmp/aiplat-frontend.log 2>&1 &
FRONTEND_PID=$!
echo "PID: $FRONTEND_PID"

sleep 2
for i in 1 2 3 4 5; do
    curl -s http://localhost:5173/ >/dev/null 2>&1 && echo "✓ 前端启动成功 (5173)" && break
    echo "等待... ($i/5)"
    sleep 1
done

# 保存 PID
echo -e "$CORE_PID\n$INFRA_PID\n$PLATFORM_PID\n$APP_PID\n$MGMT_PID\n$FRONTEND_PID" > /tmp/aiplat.pids

echo ""
echo "============================================================"
echo "  ✓ 启动完成"
echo "============================================================"
echo ""
echo "服务:"
echo "  - core:        http://localhost:8002"
echo "  - infra:       http://localhost:8001"
echo "  - platform:    http://localhost:8003"
echo "  - app:         http://localhost:8004"
echo "  - management:  http://localhost:8000"
echo "  - 前端:        http://localhost:5173"
echo ""
echo "停止: ./stop.sh"
