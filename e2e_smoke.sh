#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# 可选：从本地环境文件加载（避免把 key 写进脚本/提交到 git）
# 优先级：.env.e2e > .env.local > .env
for f in ".env.e2e" ".env.local" ".env"; do
  if [ -f "$f" ]; then
    echo "Loading env from $f"
    set -a
    # shellcheck disable=SC1090
    source "$f"
    set +a
    break
  fi
done

echo "Running aiPlat E2E smoke..."
python3 e2e_smoke.py
