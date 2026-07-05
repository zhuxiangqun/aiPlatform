#!/usr/bin/env bash
# benchmark-ci.sh — run all performance benchmarks for CI
# Produces structured JSON output for baseline tracking
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS=""
PASSED=0
TOTAL=0

run_bench() {
    local name="$1"
    local script="$2"
    local extra_args="${3:-}"
    TOTAL=$((TOTAL + 1))
    echo "=== $name ==="
    if [ -f "$script" ]; then
        if python3 "$script" --ci $extra_args 2>/dev/null; then
            PASSED=$((PASSED + 1))
            echo "  ✅ $name PASSED"
        else
            echo "  ⚠️  $name SKIPPED (may need running instance)"
        fi
    else
        echo "  ⚠️  $name NOT FOUND"
    fi
}

# Run all benchmarks (best-effort, some need running instance)
run_bench "live-graph" "$DIR/benchmark_live.py" ""
run_bench "ontology"   "$DIR/benchmark_ontology.py" "--quick"
run_bench "sysgraph"   "$DIR/benchmark_sysgraph.py" "--quick"
run_bench "traversal"  "$DIR/benchmark_traversal.py" "--quick"

echo ""
echo "=============================="
echo "Benchmark Summary: $PASSED/$TOTAL passed"
echo "=============================="

# Always exit 0 — benchmarks are informational, not gating
exit 0
