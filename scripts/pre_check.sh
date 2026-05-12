#!/bin/bash
# pre_check.sh — Pre-PR 自检
# commit 前自动拦截：语法错误、架构违规、新文件无 caller、临时标记过多
set -eu

CHANGED=$(git diff --cached --name-only --diff-filter=AM | grep '\.py$' || true)

echo "═══ PRE-CHECK ═══"

# 1) 语法检查
if [ -n "$CHANGED" ]; then
  FAILS=0
  for f in $CHANGED; do
    python -m py_compile "$f" 2>/dev/null || { echo "  FAIL: $f (syntax)"; FAILS=1; }
  done
  if [ "$FAILS" -eq 0 ]; then
    echo "  PASS: py_compile ($(echo "$CHANGED" | wc -l | tr -d ' ') files)"
  else
    exit 1
  fi
fi

# 2) 架构规约
bash scripts/architecture_guard.sh

# 3) 新建文件接线检查
NEW_FILES=$(git diff --cached --name-only --diff-filter=A | grep '\.py$' || true)
if [ -n "$NEW_FILES" ]; then
  echo "  wire check ($(echo "$NEW_FILES" | wc -l | tr -d ' ') new files)..."
  for f in $NEW_FILES; do
    MODULE_NAME=$(basename "$f" .py)
    if [ "$MODULE_NAME" = "__init__" ]; then
      continue
    fi
    # 搜索调用者：排除自身、测试、__pycache__
    CALLERS=$(grep -rl "$MODULE_NAME" aiPlat-core/core/ --include='*.py' 2>/dev/null \
      | grep -v "$f" | grep -v __pycache__ | grep -v '/tests/' || true)
    if [ -z "$CALLERS" ]; then
      echo "  FAIL: $f has 0 production callers"
      exit 1
    fi
    echo "    $MODULE_NAME: $(echo "$CALLERS" | wc -l | tr -d ' ') caller(s)"
  done
  echo "  PASS: wire check"
else
  echo "  PASS: wire check (no new files)"
fi

# 4) 临时标记检查
TODO_COUNT=0
if [ -n "$CHANGED" ]; then
  TODO_COUNT=$(grep -rn 'TODO\|FIXME\|HACK' $CHANGED 2>/dev/null | wc -l | tr -d ' ' || echo 0)
fi
if [ "$TODO_COUNT" -gt 3 ]; then
  echo "  WARN: $TODO_COUNT temporary markers (TODO/FIXME/HACK) in changed files"
else
  echo "  PASS: temp markers (${TODO_COUNT} in changed files)"
fi

echo "═══ PRE-CHECK PASSED ═══"
