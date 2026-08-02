#!/bin/bash
set -euo pipefail
# Pre-commit guard: detect hardcoded business concepts in engine layer
# Installed: copy to .git/hooks/pre-commit or invoke via husky/lint-staged

echo "=== Pre-commit: Engine layer compliance ==="
VIOLATIONS=0

# Rule 1: No new Chinese prompts in engine (must use prompt_loader or SKILL.md)
NEW_CN=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | xargs grep -l '你是\|你是一个\|请将\|请基于\|现在是' 2>/dev/null | grep 'core/harness/execution/' | grep -v 'test_\|prompt_loader\|_sync_resolve' || true)
if [ -n "$NEW_CN" ]; then
  echo "❌ R1: Chinese prompts found in engine layer: $NEW_CN"
  echo "   Fix: Move to prompt_loader.py or SKILL.md"
  VIOLATIONS=$((VIOLATIONS+1))
else echo "✅ R1: No Chinese prompts in engine"
fi

# Rule 2: No hardcoded artifact key tuples
NEW_KEY=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | xargs grep -l '"architecture".*"code".*"test_report"\|state\.get("architecture"\|state\.get("code"\|state\.get("test_report"' 2>/dev/null | grep 'core/harness/execution/' | grep -v 'test_\|_run_stage_skill\|#\|snapshot' || true)
if [ -n "$NEW_KEY" ]; then
  echo "❌ R2: Hardcoded artifact keys in engine: $NEW_KEY"
  echo "   Fix: Use stage.output_artifact or config.stages iteration"
  VIOLATIONS=$((VIOLATIONS+1))
else echo "✅ R2: No hardcoded artifact keys"
fi

# Rule 3: No direct sys_llm_generate with f-string user messages
NEW_LLM=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | xargs grep -l 'sys_llm_generate.*{"role".*"user".*f"' 2>/dev/null | grep 'core/harness/execution/' | grep -v 'test_\|_run_stage_skill\|compressor\|inference\|target_continuity' || true)
if [ -n "$NEW_LLM" ]; then
  echo "❌ R3: Direct sys_llm_generate with f-string in engine: $NEW_LLM"
  echo "   Fix: Route through _run_stage_skill or prompt_loader._sync_resolve()"
  VIOLATIONS=$((VIOLATIONS+1))
else echo "✅ R3: No direct sys_llm_generate with f-string"
fi

echo ""
if [ $VIOLATIONS -gt 0 ]; then
  echo "❌ $VIOLATIONS violation(s) — fix before commit"
  exit 1
fi
echo "✅ Engine layer clean"
exit 0
