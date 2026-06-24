#!/bin/bash
# verify_doc_sync.sh — Check that CAPABILITIES.md stays in sync with code
#
# Trigger points:
#   1. New public class/function added → must have CAPABILITIES.md entry
#   2. Module renamed/deleted → must update CAPABILITIES.md
#   3. git diff detects .py changes → warn if CAPABILITIES.md untouched
#
# Usage: bash scripts/verify_doc_sync.sh [--ci]
#   --ci    Exit with non-zero on violations

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
CAPABILITIES="$WORKSPACE/AIPLAT_CAPABILITIES.md"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CI_MODE=false
if [ "${1:-}" = "--ci" ]; then CI_MODE=true; fi

VIOLATIONS=0

# ══════════════════════════════════════════════════════════════
# Rule 1: New module files → must be referenced in CAPABILITIES.md
# ══════════════════════════════════════════════════════════════
check_new_modules() {
    echo ""
    echo "━━━ Rule 1: New modules referenced in CAPABILITIES.md ━━━"

    # Find recently created .py files (within last 7 days) in core harness
    # that are NOT __init__.py and NOT test files
    local new_files=$(
        find "$WORKSPACE/aiPlat-core/core/harness" \
            -name "*.py" -not -name "__init__.py" -not -path "*/tests/*" \
            -newer "$CAPABILITIES" -mtime -7 2>/dev/null | head -20
    )

    if [ -z "$new_files" ]; then
        echo -e "  ${GREEN}✓${NC} No new unreferenced modules"
        return
    fi

    for f in $new_files; do
        local basename="${f##*/}"
        local basename_noext="${basename%.py}"
        if ! grep -qi "$basename_noext" "$CAPABILITIES" 2>/dev/null; then
            echo -e "  ${YELLOW}⚠${NC} 新模块未被 CAPABILITIES.md 引用: $basename_noext"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    done
}

# ══════════════════════════════════════════════════════════════
# Rule 2: CAPABILITIES.md entries → verify code files exist
# ══════════════════════════════════════════════════════════════
check_stale_entries() {
    echo ""
    echo "━━━ Rule 2: CAPABILITIES.md entries have valid code paths ━━━"

    # Extract code file references from CAPABILITIES.md
    # Pattern: `module/file.py` or `module/file.py:123`
    local refs=$(grep -oE '`[a-zA-Z0-9_/.-]+\.py(:[0-9]+)?`' "$CAPABILITIES" 2>/dev/null | \
                 tr -d '`' | sort -u)

    local stale=0
    for ref in $refs; do
        # Strip line number suffix (e.g. :123)
        local clean_ref="${ref%:*}"
        local basename="${clean_ref##*/}"

        # Search broadly for the file across all project dirs
        local found=$(find "$WORKSPACE/aiPlat-core" "$WORKSPACE/aiPlat-platform" \
            "$WORKSPACE/aiPlat-infra" "$WORKSPACE/aiPlat-management" "$WORKSPACE/scripts" \
            -name "$basename" -not -path "*/__pycache__/*" 2>/dev/null | head -1)

        if [ -z "$found" ]; then
            echo -e "  ${YELLOW}⚠${NC} CAPABILITIES.md 引用文件未找到: $ref"
            stale=$((stale + 1))
            [ $stale -ge 10 ] && break  # cap at 10 violations
        fi
    done

    if [ "$stale" -eq 0 ]; then
        echo -e "  ${GREEN}✓${NC} All CAPABILITIES.md code references valid"
    else
        VIOLATIONS=$((VIOLATIONS + stale))
    fi
}

# ══════════════════════════════════════════════════════════════
# Rule 3: git diff shows .py changes → CAPABILITIES.md updated?
# ══════════════════════════════════════════════════════════════
check_git_diff_sync() {
    echo ""
    echo "━━━ Rule 3: Recent code changes reflected in CAPABILITIES.md ━━━"

    if ! git -C "$WORKSPACE" rev-parse --git-dir >/dev/null 2>&1; then
        echo "  (not a git repo, skipping)"
        return
    fi

    # Check if there are unstaged .py changes
    local py_changes=$(git -C "$WORKSPACE" diff --name-only 2>/dev/null | grep '\.py$' | grep -v __pycache__ | head -5 || true)
    local caps_changed=$(git -C "$WORKSPACE" diff --name-only 2>/dev/null | grep -c "CAPABILITIES.md\|ROADMAP.md" || echo "0")

    if [ -n "$py_changes" ] && [ "$caps_changed" -eq 0 ]; then
        echo -e "  ${YELLOW}⚠${NC} 检测到 .py 变更但 CAPABILITIES.md/ROADMAP.md 未同步更新"
        echo "  变更文件:"
        for f in $py_changes; do
            echo "    $f"
        done
        VIOLATIONS=$((VIOLATIONS + 1))
    else
        echo -e "  ${GREEN}✓${NC} Code and docs in sync"
    fi
}

# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  DOCUMENT SYNC CHECK — CAPABILITIES.md ↔ Code"
echo "═══════════════════════════════════════════════════════════════"

check_new_modules
check_stale_entries
check_git_diff_sync

echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ "$VIOLATIONS" -eq 0 ]; then
    echo -e "${GREEN}═══ DOC SYNC PASSED — all checks clear ═══${NC}"
    exit 0
else
    echo -e "${RED}═══ DOC SYNC FAILED: $VIOLATIONS violation(s) ═══${NC}"
    echo ""
    echo "  修复方法:"
    echo "    1. 更新 AIPLAT_CAPABILITIES.md 添加新能力"
    echo "    2. 更新 AIPLAT_ROADMAP.md 评分（如适用）"
    echo "    3. 重新运行: bash scripts/verify_doc_sync.sh"
    exit 1  # always block — doc sync is mandatory
fi
