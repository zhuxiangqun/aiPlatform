#!/usr/bin/env bash
# ============================================================================
# caller_verify.sh — 接线完成度验证脚本
#
# 预扫描全仓符号引用，然后快速检测 0 调用者的死代码。
#
# Usage: bash scripts/caller_verify.sh
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VIOLATIONS=0
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

_log() { echo -e "$@" >&2; }

# ------------------------------------------------------------------
# Step 1: Build symbol → caller_files index (one scan)
# ------------------------------------------------------------------
_log "  Building symbol index..."
find "$WORKSPACE/aiPlat-core" "$WORKSPACE/aiPlat-platform" "$WORKSPACE/aiPlat-app" \
    -name '*.py' -not -path '*/__pycache__/*' -not -path '*/tests/*' \
    -not -name 'conftest.py' 2>/dev/null | head -500 > "$TMPDIR/all_files.txt"

# Build a quick index: for each keyword, check which files mention it
# Use a simple inverted-index approach with grep -lF (fast fixed-string search)
build_index() {
    local keyword="$1"
    grep -lF "$keyword" $(cat "$TMPDIR/all_files.txt") 2>/dev/null | wc -l | tr -d ' '
}

# ------------------------------------------------------------------
# Extract public symbols from a Python file
# ------------------------------------------------------------------
extract_symbols() {
    local file="$1"
    python3 -c "
import ast
try:
    tree = ast.parse(open('$file').read())
except Exception:
    pass
else:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
            print(f'{node.name}')
        elif isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
            print(f'{node.name}')
" 2>/dev/null || true
}

# ------------------------------------------------------------------
# Check if symbol has callers (quick grep in target dirs only)
# ------------------------------------------------------------------
has_callers() {
    local symbol="$1"
    local self_basename="$2"
    # Search only in non-test Python files, exclude self file
    local hits
    hits=$(grep -rlF "$symbol" "$WORKSPACE/aiPlat-core" "$WORKSPACE/aiPlat-platform" "$WORKSPACE/aiPlat-app" \
        --include='*.py' 2>/dev/null \
        | grep -v __pycache__ \
        | grep -v "$self_basename" \
        | grep -v '/tests/' \
        | grep -v 'conftest\.py' \
        | wc -l | tr -d ' ')
    [ "${hits:-0}" -gt 0 ]
}

# ===================================================================
# Check: key harness files for dead public symbols
# ===================================================================
HARNESS_DIR="$WORKSPACE/aiPlat-core/core/harness"

PRIORITY_FILES=(
    "infrastructure/infra_bridge.py"
    "execution/team_planner.py"
    "execution/conditional.py"
    "execution/debate.py"
    "execution/renderer.py"
    "execution/router.py"
    "execution/sandbox.py"
    "execution/pipeline_engine.py"
    "execution/loop.py"
    "memory/manager.py"
    "memory/embedding.py"
    "knowledge/db.py"
    "knowledge/embedder.py"
    "knowledge/retriever.py"
    "document/parsers.py"
    "document/ocr.py"
    "document/transcriber.py"
)

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Caller Verification — Dead Code Detection"
echo "═══════════════════════════════════════════════════════════════"
echo ""

for rel_path in "${PRIORITY_FILES[@]}"; do
    f="$HARNESS_DIR/$rel_path"
    [ -f "$f" ] || continue
    basename_f="$(basename "$f")"

    while IFS= read -r name; do
        [ -z "$name" ] && continue
        if ! has_callers "$name" "$basename_f"; then
            _log "  ${RED}→${NC} $rel_path: $name — ${RED}0 callers${NC}"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    done < <(extract_symbols "$f")
done

# ===================================================================
# Summary
# ===================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ "$VIOLATIONS" -gt 0 ]; then
    echo -e "${RED}═══ CALLER VERIFY FAILED: $VIOLATIONS dead symbols ═══${NC}"
    echo ""
    echo "  Fix: wire to production path, add TODO, or remove dead code."
    exit 1
else
    echo -e "${GREEN}═══ CALLER VERIFY PASSED — all symbols have callers ═══${NC}"
    exit 0
fi
