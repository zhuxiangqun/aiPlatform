#!/usr/bin/env bash
# wait_for_health.sh — 轮询等待所有服务健康
#
# 用法: bash scripts/wait_for_health.sh [--timeout 60]
set -euo pipefail

TIMEOUT="${1:-60}"
BASE_CORE="${2:-http://localhost:8002}"
BASE_MGMT="${3:-http://localhost:8000}"
BASE_PLAT="${4:-http://localhost:8003}"

echo "等待服务就绪 (timeout=${TIMEOUT}s)..."

for i in $(seq 1 "$TIMEOUT"); do
    core_ok=false; mgmt_ok=false; plat_ok=false

    curl -sf -m2 "$BASE_CORE/api/core/health" >/dev/null 2>&1 && core_ok=true
    curl -sf -m2 "$BASE_MGMT/api/health" >/dev/null 2>&1 && mgmt_ok=true
    curl -sf -m2 "$BASE_PLAT/api/platform/health" >/dev/null 2>&1 && plat_ok=true

    if $core_ok && $mgmt_ok && $plat_ok; then
        echo "✅ 全部服务就绪 (${i}s)"
        exit 0
    fi

    printf "\r  [%3d/%3d] core=%s mgmt=%s plat=%s" "$i" "$TIMEOUT" \
        "$($core_ok && echo ✓ || echo ✗)" "$($mgmt_ok && echo ✓ || echo ✗)" "$($plat_ok && echo ✓ || echo ✗)"
    sleep 1
done

echo ""
echo "❌ 超时 — 部分服务未就绪"
exit 1
