#!/bin/bash
# git pre-commit hook — autoreview code before committing
# Place this file at: .git/hooks/pre-commit
# Make executable: chmod +x .git/hooks/pre-commit

API_URL="${AIPLAT_API_URL:-http://localhost:8000}"
API_PATH="/api/core/skills/autoreview/execute"

echo "🔍 Running autoreview..."

RESPONSE=$(curl -s -X POST "${API_URL}${API_PATH}" \
  -H "Content-Type: application/json" \
  -d '{"target": "diff", "focus": "comprehensive", "mode": "quick"}')

CLEAN=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('clean','false'))" 2>/dev/null)

if [ "$CLEAN" = "True" ]; then
    echo "✅ autoreview clean — proceeding with commit"
    exit 0
else
    echo "❌ autoreview found issues:"
    echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('report',{}); print(f'  P0={r.get(\"p0_count\",0)} P1={r.get(\"p1_count\",0)} P2={r.get(\"p2_count\",0)} score={r.get(\"score\",0)}')" 2>/dev/null
    echo ""
    echo "Use 'git commit --no-verify' to bypass, or fix issues and retry."
    exit 1
fi
