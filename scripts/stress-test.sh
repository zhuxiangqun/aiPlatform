#!/usr/bin/env bash
# stress-test.sh — concurrent load test for aiPlat APIs
# Measures P95 latency, throughput, error rate under load
# Usage: bash scripts/stress-test.sh [BASE_URL] [concurrency]
#
# Requires: ab (Apache Bench) or wrk. Falls back to basic curl loop.

set -euo pipefail

BASE="${1:-http://localhost:8000}"
CONC="${2:-10}"
REQ="${3:-100}"

echo "=== aiPlat Stress Test ==="
echo "Target: $BASE"
echo "Concurrency: $CONC, Requests: $REQ"
echo ""

# Test endpoints
ENDPOINTS=(
    "GET /api/diagnostics/health/all"
    "GET /api/core/workspace/agents"
)

if command -v ab &>/dev/null; then
    for ep in "${ENDPOINTS[@]}"; do
        method=$(echo "$ep" | cut -d' ' -f1)
        path=$(echo "$ep" | cut -d' ' -f2-)
        echo "--- $method $path ---"
        ab -n "$REQ" -c "$CONC" -q "$BASE$path" 2>&1 | grep -E 'Requests|Time per|Transfer|Failed|P50|P95|P99' || true
    done
elif command -v wrk &>/dev/null; then
    for ep in "${ENDPOINTS[@]}"; do
        echo "--- $ep ---"
        wrk -c "$CONC" -d 10s --latency "$BASE${ep#* }" 2>&1 | head -15
    done
else
    echo "No stress tool found (ab/wrk). Running basic sequential test..."
    start=$(date +%s)
    success=0
    for i in $(seq 1 "$REQ"); do
        curl -s -o /dev/null -w "%{http_code}" "$BASE/api/diagnostics/health/all" --connect-timeout 5 --max-time 10 2>/dev/null | grep -q 200 && success=$((success+1))
    done
    elapsed=$(($(date +%s) - start))
    rate=$(echo "scale=1; $success / $elapsed" | bc 2>/dev/null || echo "N/A")
    echo "Requests: $REQ, Success: $success, Time: ${elapsed}s, Rate: ${rate}/s"
fi

echo ""
echo "=== Stress Test Complete ==="
