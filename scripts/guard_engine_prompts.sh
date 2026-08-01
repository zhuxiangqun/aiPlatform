#!/bin/bash
set -euo pipefail
# Guard: detect hardcoded business concepts / bypasses in pipeline engine
# Only checks pipeline_engine.py — other engine files use sys_llm_generate
# legitimately through ReAct loop / inference paths.

TARGET="aiPlat-core/core/harness/execution/pipeline_engine.py"
violations=0

echo "=== Pipeline engine architecture compliance ==="

# Rule 1: No Chinese system prompts (bypassing SKILL.md)
echo -n "Rule 1 (prompts in engine): "
count=$(grep -c '你是\|你是一个\|你是一位\|You are a' "$TARGET" 2>/dev/null || echo 0)
count=$(echo "$count" | tr -d ' ')
if [ "$count" -gt 0 ]; then
    echo "❌ $count violation(s) — prompts belong in SKILL.md, not engine"
    grep -n '你是\|你是一个\|你是一位\|You are a' "$TARGET"
    violations=$((violations + count))
else
    echo "✅"
fi

# Rule 2: No hardcoded skill names (must use stage.skill_name from config)
echo -n "Rule 2 (hardcoded skill names): "
count=$(grep -c '"architecture_design"\|"code_generation"\|"test_case_generation"' "$TARGET" 2>/dev/null || echo 0)
count=$(echo "$count" | tr -d ' ')
if [ "$count" -gt 0 ]; then
    echo "❌ $count violation(s) — skill names should come from PipelineStageConfig.skill_name"
    grep -n '"architecture_design"\|"code_generation"\|"test_case_generation"' "$TARGET"
    violations=$((violations + count))
else
    echo "✅"
fi

# Rule 3: No hardcoded artifact keys
echo -n "Rule 3 (hardcoded artifact keys): "
count=$(grep -c "output_artifact.*==.*'architecture\|\.get('architecture'\|\.get('code'\|\.get('test_report'" "$TARGET" 2>/dev/null || echo 0)
count=$(echo "$count" | tr -d ' ')
if [ "$count" -gt 0 ]; then
    echo "❌ $count violation(s) — artifact keys should be config-driven"
    grep -n "output_artifact.*==.*'architecture\|\.get('architecture'\|\.get('code'\|\.get('test_report'" "$TARGET"
    violations=$((violations + count))
else
    echo "✅"
fi

echo ""
if [ "$violations" -gt 0 ]; then
    echo "❌ $violations total violations"
    exit 1
else
    echo "✅ Pipeline engine compliant"
    exit 0
fi
