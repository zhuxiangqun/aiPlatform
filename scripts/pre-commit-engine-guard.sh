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

# Rule 4: No new business state keys in engine (vs baseline)
CHANGED_ENGINE=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep 'core/harness/execution/' || true)
if [ -n "$CHANGED_ENGINE" ]; then
  BASELINE="$(dirname "$0")/baselines/engine_state_keys.txt"
  if [ -f "$BASELINE" ]; then
    NEW_KEYS=$(CHANGED_ENGINE="$CHANGED_ENGINE" BASELINE="$BASELINE" python3 -c '
import re, os, sys
baseline_path = os.environ["BASELINE"]
with open(baseline_path) as f:
    allowed = {l.split("|")[0] for l in f if l.strip() and not l.startswith("#")}
    debt_keys = {l.split("|")[0] for l in f if "|DEBT|" in l}

found = set()
# File list passed via env (newline-separated) — safe for multi-line paths.
# Match only quoted keys: state["key"] / state.get("key") — the `.` wildcard
# form matched fragments (e.g. `ke` from f-strings), so anchor on quote chars.
for fpath in os.environ.get("CHANGED_ENGINE", "").splitlines():
    if os.path.isfile(fpath):
        t = open(fpath).read()
        for m in re.finditer(r"""state\[(["'"'"'])(\w+)\1\]""", t): found.add(m.group(2))
        for m in re.finditer(r"""state\.get\((["'"'"'])(\w+)\1\)""", t): found.add(m.group(2))

new = found - allowed
for k in sorted(new):
    print(k)
' 2>/dev/null)
    if [ -n "$NEW_KEYS" ]; then
      echo "❌ R4: New state keys in engine not in baseline:"
      echo "$NEW_KEYS"
      echo "   Fix: Either (a) remove hardcoded key, (b) add to baseline as DEBT,"
      echo "        or (c) prove it's genuinely generic and add as OK"
      VIOLATIONS=$((VIOLATIONS+1))
    else echo "✅ R4: No new state key violations"
    fi
  fi
else echo "✅ R4: No engine changes"
fi

echo ""
if [ $VIOLATIONS -gt 0 ]; then
  echo "❌ $VIOLATIONS violation(s) — fix before commit"
  exit 1
fi
echo "✅ Engine layer clean"
exit 0
