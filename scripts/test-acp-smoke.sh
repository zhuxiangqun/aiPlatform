#!/bin/bash
# ACP Smoke Test — verifies the ACP server + WebSocket connectivity
# Ref: 工程落地 2.12 IDE 插件集成冒烟测试
set -euo pipefail

ACP_PORT="${AIPLAT_ACP_PORT:-8005}"
ACP_HOST="${AIPLAT_ACP_HOST:-127.0.0.1}"

echo "=== ACP Smoke Test ==="
echo "  Target: ws://${ACP_HOST}:${ACP_PORT}/acp"

FAILED=0

# Step 1: Start ACP server
echo ""
echo "[1/4] Starting ACP server..."

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/aiPlat-core/core"
PYTHONPATH="$REPO_ROOT/aiPlat-core" python -c "
import asyncio, os, sys
sys.path.insert(0, '..')
from acp.server import app
import uvicorn
uvicorn.run(app, host='${ACP_HOST}', port=${ACP_PORT}, log_level='error')
" > /tmp/acp-smoke.log 2>&1 &
ACP_PID=$!
echo "  PID: $ACP_PID"

# Wait for server
for i in $(seq 1 10); do
    if curl -sf "http://${ACP_HOST}:${ACP_PORT}/health" > /dev/null 2>&1; then
        echo "  Server UP (attempt $i)"
        break
    fi
    sleep 1
done

if ! curl -sf "http://${ACP_HOST}:${ACP_PORT}/health" > /dev/null 2>&1; then
    echo "  ❌ Server failed to start"
    cat /tmp/acp-smoke.log
    exit 1
fi

# Step 2: WebSocket status test
echo ""
echo "[2/4] Testing WebSocket status..."
STATUS=$(python3 -c "
import asyncio, json, sys
sys.path.insert(0, '.')
import websockets

async def t():
    async with websockets.connect('ws://${ACP_HOST}:${ACP_PORT}/acp') as ws:
        await ws.send(json.dumps({'type':'status'}))
        r = json.loads(await ws.recv())
        print(r.get('agent','FAIL'))
asyncio.run(t())
" 2>&1)

if echo "$STATUS" | grep -q "aiPlat"; then
    echo "  ✅ status: $STATUS"
else
    echo "  ❌ status failed: $STATUS"
    FAILED=1
fi

# Step 3: WebSocket exec test
echo ""
echo "[3/4] Testing WebSocket exec..."
EXEC_RESULT=$(python3 -c "
import asyncio, json, sys
sys.path.insert(0, '.')
import websockets

async def t():
    async with websockets.connect('ws://${ACP_HOST}:${ACP_PORT}/acp') as ws:
        await ws.send(json.dumps({'type':'exec','command':'echo ACP_SMOKE_OK'}))
        r = json.loads(await ws.recv())
        print(r.get('stdout','FAIL').strip())
asyncio.run(t())
" 2>&1)

if echo "$EXEC_RESULT" | grep -q "ACP_SMOKE_OK"; then
    echo "  ✅ exec: $EXEC_RESULT"
else
    echo "  ❌ exec failed: $EXEC_RESULT"
    FAILED=1
fi

# Step 4: Stop server
echo ""
echo "[4/4] Stopping ACP server..."
kill $ACP_PID 2>/dev/null || true
rm -f /tmp/acp-smoke.log

if [ "$FAILED" -eq 0 ]; then
    echo ""
    echo "✅ ACP Smoke Test PASSED"
    exit 0
else
    echo ""
    echo "❌ ACP Smoke Test FAILED"
    exit 1
fi
