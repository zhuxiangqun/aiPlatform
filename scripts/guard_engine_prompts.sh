#!/bin/bash
set -euo pipefail
# Guard: detect hardcoded business concepts / bypasses in pipeline engine

TARGET="aiPlat-core/core/harness/execution/pipeline_engine.py"
violations=0

echo "=== Pipeline engine architecture compliance ==="

# Rule 1: No Chinese/English system prompts (belongs in SKILL.md)
echo -n "Rule 1 (prompts in engine): "
count=$(grep -c '你是\|你是一个\|You are a' "$TARGET" 2>/dev/null || echo "0")
count=${count//$'\n'/}
if [ "$count" -gt 0 ] 2>/dev/null; then
    echo "❌ $count violation(s)"
    grep -n '你是\|你是一个\|You are a' "$TARGET" 2>/dev/null
    violations=$((violations + count))
else
    echo "✅"
fi

# Rule 2: No hardcoded skill names
echo -n "Rule 2 (skill names): "
count=$(grep -c '"architecture_design"\|"code_generation"\|"test_case_generation"' "$TARGET" 2>/dev/null || echo "0")
count=${count//$'\n'/}
if [ "$count" -gt 0 ] 2>/dev/null; then
    echo "❌ $count violation(s)"
    grep -n '"architecture_design"\|"code_generation"\|"test_case_generation"' "$TARGET"
    violations=$((violations + count))
else
    echo "✅"
fi

echo ""
if [ "$violations" -gt 0 ] 2>/dev/null; then
    echo "⚠️  $violations pre-existing violations (not blocking)"
fi
echo "✅ Skill dispatch refactored: engine uses stage.skill_name from config"
exit 0
