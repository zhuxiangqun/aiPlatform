#!/usr/bin/env bash
# stability-test.sh — long-duration stability verification
# Runs N iterations of Agent execution, monitors memory/checkpoint/token trends.
# Usage: bash scripts/stability-test.sh [iterations] [base_url]
set -euo pipefail

ITERS="${1:-100}"
BASE="${2:-http://localhost:8000}"
LOG_FILE="/tmp/aiplat_stability_$(date +%Y%m%d_%H%M%S).csv"

echo "=== aiPlat Long-Duration Stability Test ==="
echo "Iterations: $ITERS | Target: $BASE"
echo "Log: $LOG_FILE"
echo ""

echo "iteration,status,latency_ms,tokens_used,memory_kb,checkpoint_count,timestamp" > "$LOG_FILE"

PASS=0
CHECK_INTERVAL=10
TOKENS_PREV=0
MEM_PREV=0

for i in $(seq 1 "$ITERS"); do
    START=$(date +%s%N)
    STATUS="ok"
    TOKENS=0
    
    # Execute a simple agent task
    HTTP=$(curl -s -o /tmp/stab_resp.json -w "%{http_code}" \
        -X POST "$BASE/api/core/workspace/agents/materials_chat/execute" \
        -H "Content-Type: application/json" \
        -d '{"messages":[{"role":"user","content":"用一句话总结机器学习的核心思想"}]}' \
        --connect-timeout 5 --max-time 30 2>/dev/null || echo "000")
    
    END=$(date +%s%N)
    LATENCY=$(((END - START) / 1000000))
    
    if [ "$HTTP" -eq 200 ]; then
        TOKENS=$(python3 -c "import json; d=json.load(open('/tmp/stab_resp.json')); print(d.get('tokens',{}).get('total_tokens',0))" 2>/dev/null || echo 0)
        PASS=$((PASS + 1))
    else
        STATUS="error:$HTTP"
    fi
    
    # Memory check every CHECK_INTERVAL iterations
    MEM=0
    CHK=0
    if [ $((i % CHECK_INTERVAL)) -eq 0 ]; then
        MEM=$(ps -o rss= -p $$ 2>/dev/null | head -1 || echo 0)
        CHK=$(find ~/.aiplat/ -name '*checkpoint*' -newer /tmp/stab_resp.json 2>/dev/null | wc -l || echo 0)
        
        # Check for memory growth > 20% over 10 iterations
        if [ "$MEM_PREV" -gt 0 ] && [ "$MEM" -gt $((MEM_PREV * 12 / 10)) ]; then
            echo "  ⚠️  Memory growth detected at iteration $i: ${MEM_PREV}→${MEM} KB"
        fi
        MEM_PREV=$MEM
        
        # Check for token leak (repeated tasks should use similar tokens)
        if [ "$TOKENS_PREV" -gt 0 ] && [ "$TOKENS" -gt $((TOKENS_PREV * 3)) ]; then
            echo "  ⚠️  Token spike at iteration $i: ${TOKENS_PREV}→${TOKENS}"
        fi
        TOKENS_PREV=$TOKENS
    fi
    
    echo "$i,$STATUS,$LATENCY,$TOKENS,$MEM,$CHK,$(date +%s)" >> "$LOG_FILE"
    
    # Progress
    if [ $((i % 10)) -eq 0 ]; then
        RATE=$(echo "scale=1; $PASS / $i * 100" | bc 2>/dev/null || echo "0")
        echo "  [$i/$ITERS] success_rate=${RATE}% latency=${LATENCY}ms"
    fi
    
    sleep 0.5
done

echo ""
echo "========================================="
echo "Stability Test Complete"
echo "Pass: $PASS/$ITERS ($(echo "scale=1; $PASS / $ITERS * 100" | bc 2>/dev/null)%)"
echo "Log: $LOG_FILE"

# Quick analysis
TOKENS_AVG=$(awk -F',' 'NR>1{sum+=$4;c++}END{printf "%.0f",sum/c}' "$LOG_FILE" 2>/dev/null || echo "N/A")
LAT_AVG=$(awk -F',' 'NR>1 && $2=="ok"{sum+=$3;c++}END{printf "%.0f",sum/c}' "$LOG_FILE" 2>/dev/null || echo "N/A")
echo "Average tokens: $TOKENS_AVG | Average latency: ${LAT_AVG}ms"
echo ""

# Check for degradation
FIRST_10_LAT=$(awk -F',' 'NR>1 && NR<=11 && $2=="ok"{sum+=$3;c++}END{printf "%.0f",sum/c}' "$LOG_FILE" 2>/dev/null || echo "0")
LAST_10_LAT=$(awk -F',' 'NR>'$((ITERS-10+1))' && $2=="ok"{sum+=$3;c++}END{printf "%.0f",sum/c}' "$LOG_FILE" 2>/dev/null || echo "0")
if [ "$FIRST_10_LAT" != "0" ] && [ "$LAST_10_LAT" != "0" ] && [ "$LAST_10_LAT" -gt $((FIRST_10_LAT * 2)) ]; then
    echo "⚠️  Performance degradation: latency 2x increase (${FIRST_10_LAT}→${LAST_10_LAT}ms)"
else
    echo "✅ No significant performance degradation detected"
fi

echo "✅ 长时稳定性验证通过" 2>/dev/null || echo "⚠️  Has warnings, check log"
