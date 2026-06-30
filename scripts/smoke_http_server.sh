#!/usr/bin/env bash
set -euo pipefail

# Start a local HTTP server serving the smoke fixtures directory.
# Prints the base URL to stdout (e.g., http://127.0.0.1:18080) and keeps running until killed.
#
# See also: smoke_documents_ingest.sh — 文档入库冒烟测试（需此 server 先启动）

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIX_DIR="$ROOT_DIR/aiPlat-core/core/harness/smoke/fixtures"
PORT="${SMOKE_HTTP_PORT:-18080}"

cd "$FIX_DIR"

PY="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi

exec "$PY" -m http.server "$PORT" --bind 127.0.0.1

