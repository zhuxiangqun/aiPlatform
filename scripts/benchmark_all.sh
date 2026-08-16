#!/usr/bin/env bash
# Knowledge OS Performance Benchmark — unified entry point
# Usage:
#   bash scripts/benchmark_all.sh                           # full interactive
#   bash scripts/benchmark_all.sh --ci                      # CI mode (JSON output + regression check)
set -e

CI_MODE=false
DIR="${HOME}/.aiplat/test_docs"
DOMAIN="ai-knowledge"

for arg in "$@"; do
    case $arg in
        --ci) CI_MODE=true ;;
        --dir) DIR="$2"; shift ;;
        --domain) DOMAIN="$2"; shift ;;
    esac
    shift 2>/dev/null || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHONPATH="$PROJECT/aiPlat-core:$PROJECT/aiPlat-infra"
export PYTHONPATH
BASELINE="${HOME}/.aiplat/benchmark_baseline.json"

if [ "$CI_MODE" = false ]; then
    echo "============================================"
    echo "  KNOWLEDGE OS PERFORMANCE BENCHMARK"
    echo "============================================"
    echo ""
fi

PASS=0
FAIL=0
PIPELINE_P95=""
TRAV_P95_MS=""
RECALL_VAL=""
AUDIT_ACC=""
ECE_VAL=""

# ── 1. Pipeline Latency ──
[ "$CI_MODE" = false ] && echo "-- 1. Pipeline Latency --"
PIPELINE_OUT=$(python3 "$SCRIPT_DIR/benchmark_ontology.py" --dir "$DIR" --domain "$DOMAIN" 2>/dev/null || echo "")
PIPELINE_P95=$(echo "$PIPELINE_OUT" | grep "P95:" | grep -oE '[0-9]+\.[0-9]+s' | head -1 | sed 's/s//')
if [ -n "$PIPELINE_P95" ] && python3 -c "exit(0 if ${PIPELINE_P95:-0} < 60 else 1)" 2>/dev/null; then
    PASS=$((PASS+1))
    [ "$CI_MODE" = false ] && echo "  PASS  P95=${PIPELINE_P95}s < 60s"
else
    FAIL=$((FAIL+1))
    [ "$CI_MODE" = false ] && echo "  FAIL  P95=${PIPELINE_P95:-N/A}"
fi

# ── 2. Traversal Latency ──
[ "$CI_MODE" = false ] && echo "-- 2. Graph Traversal --"
TRAV_OUT=$(python3 "$SCRIPT_DIR/benchmark_traversal.py" --runs 50 2>/dev/null || echo "")
TRAV_P95_MS=$(echo "$TRAV_OUT" | grep "Max P95" | grep -oE '[0-9]+\.[0-9]+ms' | head -1 | sed 's/ms//')
if [ -n "$TRAV_P95_MS" ] && python3 -c "exit(0 if ${TRAV_P95_MS:-0} < 500 else 1)" 2>/dev/null; then
    PASS=$((PASS+1))
    [ "$CI_MODE" = false ] && echo "  PASS  P95=${TRAV_P95_MS}ms < 500ms"
else
    FAIL=$((FAIL+1))
fi

# ── 3. Retrieval Recall ──
[ "$CI_MODE" = false ] && echo "-- 3. Retrieval Recall --"
RECALL_OUT=$(python3 "$SCRIPT_DIR/eval_retrieval.py" 2>/dev/null || echo "")
RECALL_VAL=$(echo "$RECALL_OUT" | grep "Actual:" | grep -oE '[0-9]+\.[0-9]+' | head -1)
if [ -n "$RECALL_VAL" ] && python3 -c "exit(0 if ${RECALL_VAL:-0} >= 0.85 else 1)" 2>/dev/null; then
    PASS=$((PASS+1))
    [ "$CI_MODE" = false ] && echo "  PASS  Recall@10=${RECALL_VAL} > 0.85"
else
    FAIL=$((FAIL+1))
fi

# ── 4. State Transition ──
[ "$CI_MODE" = false ] && echo "-- 4. State Transition --"
AUDIT_OUT=$(python3 "$SCRIPT_DIR/audit_reasoning_paths.py" --domain "$DOMAIN" --sample 50 --auto --output /tmp/audit_ci.csv 2>/dev/null || echo "")
AUDIT_ACC=$(echo "$AUDIT_OUT" | grep -oE '[0-9]+\.[0-9]+%' | head -1 | sed 's/%//')
if [ -n "$AUDIT_ACC" ] && python3 -c "exit(0 if ${AUDIT_ACC:-0} > 80 else 1)" 2>/dev/null; then
    PASS=$((PASS+1))
    [ "$CI_MODE" = false ] && echo "  PASS  ${AUDIT_ACC}% > 80%"
else
    FAIL=$((FAIL+1))
fi

# ── 5. Confidence Calibration ──
[ "$CI_MODE" = false ] && echo "-- 5. Confidence Calibration --"
CAL_OUT=$(python3 "$SCRIPT_DIR/eval_calibration.py" 2>/dev/null || echo "")
ECE_VAL=$(echo "$CAL_OUT" | grep "ECE" | grep -oE '[0-9]+\.[0-9]+' | head -1)
if [ -n "$ECE_VAL" ] && python3 -c "exit(0 if ${ECE_VAL:-0} < 0.1 else 1)" 2>/dev/null; then
    PASS=$((PASS+1))
    [ "$CI_MODE" = false ] && echo "  PASS  ECE=${ECE_VAL} < 0.10"
else
    FAIL=$((FAIL+1))
fi

# ── 6. Memory Compression Efficiency (v4.0) ──
[ "$CI_MODE" = false ] && echo "-- 6. Memory Compression --"
if python3 "$SCRIPT_DIR/benchmark_memory.py" --ci 2>/dev/null; then
    PASS=$((PASS+1))
    [ "$CI_MODE" = false ] && echo "  PASS  memory compression active"
else
    [ "$CI_MODE" = false ] && echo "  WARN  memory compression inactive or not enough samples"
fi

# ── Save results ──
RESULTS_JSON="${HOME}/.aiplat/benchmark_results.json"
python3 -c "
import json
d = {'pipeline_p95':'${PIPELINE_P95}','traversal_p95_ms':'${TRAV_P95_MS}',
     'retrieval_recall':'${RECALL_VAL}','state_accuracy':'${AUDIT_ACC}',
     'calibration_ece':'${ECE_VAL}','pass':${PASS},'fail':${FAIL}}
with open('${RESULTS_JSON}','w') as f:
    json.dump(d, f, indent=2)
" 2>/dev/null

# ── CI: Regression check ──
if [ "$CI_MODE" = true ]; then
    REGRESSION=0
    if [ -f "$BASELINE" ]; then
        BASELINE_P95=$(python3 -c "import json; d=json.load(open('${BASELINE}')); print(d.get('pipeline_p95','0'))" 2>/dev/null || echo "0")
            if [ -n "$PIPELINE_P95" ] && [ -n "$BASELINE_P95" ]; then
            DEG=$(python3 -c "print(round((${PIPELINE_P95} - ${BASELINE_P95}) / ${BASELINE_P95} * 100, 1))" 2>/dev/null || echo "0")
            # Only flag if baseline > 0.5s AND degradation > 10%
            if python3 -c "exit(0 if ${BASELINE_P95:-0} > 0.5 and ${DEG:-0} > 10 else 1)" 2>/dev/null; then
                echo "  WARN Pipeline P95 degraded ${DEG}% (${BASELINE_P95}s → ${PIPELINE_P95}s)"
                REGRESSION=1
            fi
        fi
    fi
    cp "$RESULTS_JSON" "$BASELINE" 2>/dev/null
    if [ "$FAIL" -gt 0 ] || [ "$REGRESSION" -eq 1 ]; then
        exit 1
    else
        echo "  PASS $PASS metrics, 0 regressions"
    fi
else
    echo ""
    echo "============================================"
    echo "  COMPLETE  ($PASS/$((PASS+FAIL)) pass)"
    echo "============================================"
fi
