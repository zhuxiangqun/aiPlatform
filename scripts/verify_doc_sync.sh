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

set -uo pipefail  # -e removed: explicit exit handling below

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
    echo "━━━ Rule 2: CAPABILITIES path existence (delegated) ━━━"
    # Per-ref `find` over the monorepo was O(refs × tree) and hung pre-commit.
    # Path / line checks live in verify_capability_truth.py (Step 2–4 below).
    echo -e "  ${GREEN}✓${NC} Deferred to capability truth gate (verify_capability_doc)"
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
    # Also check .tsx/.ts changes (frontend)
    local tsx_changes=$(git -C "$WORKSPACE" diff --name-only 2>/dev/null | grep -E '\.(tsx|ts)$' | grep -v '\.d\.ts$' | grep -v node_modules | head -5 || true)
    local caps_changed=$(git -C "$WORKSPACE" diff --name-only 2>/dev/null | grep -c "CAPABILITIES.md\|ROADMAP.md" || true)
    caps_changed=${caps_changed:-0}

    if [ -n "$py_changes" ] && [ "$caps_changed" -eq 0 ]; then
        echo -e "  ${YELLOW}⚠${NC} 检测到 .py 变更但 CAPABILITIES.md/ROADMAP.md 未同步更新"
        echo "  变更文件:"
        for f in $py_changes; do
            echo "    $f"
        done
        VIOLATIONS=$((VIOLATIONS + 1))
    elif [ -n "$tsx_changes" ] && [ "$caps_changed" -eq 0 ]; then
        echo -e "  ${YELLOW}⚠${NC} 检测到 .tsx/.ts 变更但 CAPABILITIES.md/ROADMAP.md 未同步更新"
        echo "  变更文件:"
        for f in $tsx_changes; do
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

# ══════════════════════════════════════════════════════════════
# Rule 4: CAPABILITIES.md changed → downstream docs sync check
# ══════════════════════════════════════════════════════════════
check_downstream_numeric_sync() {
    caps_count=$(grep -oE '[0-9]+(项能力)' "$CAPABILITIES" 2>/dev/null | grep -oE '[0-9]+' | head -1)
    if [ -z "$caps_count" ]; then
        echo -e "  ${YELLOW}⚠${NC} Cannot extract capability count from CAPABILITIES.md"
        return
    fi
    downstream_files=(
        "$WORKSPACE/docs/DOCUMENT_SYSTEM.md"
        "$WORKSPACE/AIPLAT_ROADMAP.md"
        "$WORKSPACE/CLAUDE.md"
    )
    for doc in "${downstream_files[@]}"; do
        [ ! -f "$doc" ] && continue
        doc_count=$(grep -oE '[0-9]+(项能力)' "$doc" 2>/dev/null | grep -oE '[0-9]+' | head -1)
        if [ -n "$doc_count" ] && [ "$doc_count" != "$caps_count" ]; then
            echo -e "  ${RED}⚠${NC} $(basename "$doc"): hardcoded count $doc_count ≠ CAPABILITIES.md actual $caps_count"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    done
}
check_downstream_numeric_sync

# ══════════════════════════════════════════════════════════════
# Rule 5: management/docs claims vs code reality
# ══════════════════════════════════════════════════════════════
check_management_docs() {
    echo ""
    echo "━━━ Rule 5: management/docs claims vs code ━━━"

    # 5a: Layer 2 — docs say "预留" but platform has endpoints
    local plat_endpoints
    plat_endpoints=$(grep -r '@router\.\(get\|post\|put\|delete\|patch\)' "$WORKSPACE/aiPlat-platform/apps/" --include='*.py' 2>/dev/null | wc -l | tr -d ' ')
    for doc in "$WORKSPACE/aiPlat-management/docs/core/index.md" "$WORKSPACE/aiPlat-management/docs/infra/index.md"; do
        [ ! -f "$doc" ] && continue
        if grep -q 'Layer 2.*预留\|Layer 2.*待实施' "$doc" 2>/dev/null; then
            echo -e "  ${RED}⚠${NC} $(basename $doc): Layer 2 标注为'预留/待实施', 但 platform 有 $plat_endpoints 个端点"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    done

    # 5b: Tech stack — PostgreSQL+Redis claimed but SQLite is primary
    local sqlite_refs
    sqlite_refs=$(grep -r 'sqlite3\|SQLite\|aqlite\|sqlite_' "$WORKSPACE/aiPlat-core/core/" --include='*.py' 2>/dev/null | wc -l | tr -d ' ')
    local pg_refs
    pg_refs=$(grep -r 'psycopg2\|PostgreSQL\|postgresql' "$WORKSPACE/aiPlat-core/core/" --include='*.py' 2>/dev/null | wc -l | tr -d ' ')
    local index_doc="$WORKSPACE/aiPlat-management/docs/index.md"
    if [ -f "$index_doc" ]; then
        if grep -q 'PostgreSQL.*Redis' "$index_doc" 2>/dev/null && ! grep -q 'SQLite\|sqlite' "$index_doc" 2>/dev/null; then
            echo -e "  ${YELLOW}⚠${NC} index.md: 标注 PostgreSQL+Redis 为存储 (未提 SQLite), 但代码中 SQLite=$sqlite_refs 处, PostgreSQL=$pg_refs 处"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    fi

    # 5c: overview — "reserved" status vs actual endpoints
    local overview="$WORKSPACE/aiPlat-management/docs/overview.md"
    if [ -f "$overview" ]; then
        if grep -q '"platform".*"reserved"' "$overview" 2>/dev/null && [ "$plat_endpoints" -gt 10 ]; then
            echo -e "  ${RED}⚠${NC} overview.md: platform status='reserved', 但实际有 $plat_endpoints 个端点"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
        local core_endpoints
        core_endpoints=$(grep -r '@router\.\(get\|post\|put\|delete\|patch\)' "$WORKSPACE/aiPlat-core/core/api/routers/" --include='*.py' 2>/dev/null | wc -l | tr -d ' ')
        if grep -q '"core".*"reserved"' "$overview" 2>/dev/null && [ "$core_endpoints" -gt 10 ]; then
            echo -e "  ${RED}⚠${NC} overview.md: core status='reserved', 但实际有 $core_endpoints 个端点"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    fi
}
check_management_docs

# ══════════════════════════════════════════════════════════════
# Rule 6: research docs status-markers vs code reality (doc→code 对账)
# 调用独立脚本 scripts/check_research_docs_freshness.py
# 扫描 docs/research/*.md 状态标记与代码符号引用，验证不矛盾/不过时。
# WARNING 级，--ci 时阻断（防止专项审计文档停在旧时点）。
# ══════════════════════════════════════════════════════════════
check_research_docs_freshness() {
    echo ""
    echo "━━━ Rule 6: research docs status markers vs code ━━━"
    local out rc
    out=$(python3 "$WORKSPACE/scripts/check_research_docs_freshness.py" "$WORKSPACE" 2>&1)
    rc=$?
    echo "$out"
    if [ "$rc" -gt 0 ] && [ "${CI_MODE:-}" = "true" ]; then
        VIOLATIONS=$((VIOLATIONS + rc))
    elif [ "$rc" -gt 0 ]; then
        echo -e "  ${YELLOW}(WARNING — Rule 6 提示，本地不阻断; CI 强制)${NC}"
    fi
}
check_research_docs_freshness

# ══════════════════════════════════════════════════════════════
# Step 2/3 MUST run before the final exit (were previously dead code).
# Pre-commit also calls these scripts directly; keep a single full path here.
# ══════════════════════════════════════════════════════════════

# Step 2–4: Unified capability truth gate (paths / consistency / registry / matrix / gap)
# Source of truth = repo source. Soft warnings never alone fail. See verify_capability_truth.py.
echo ""
echo -e "${YELLOW}═══ Step 2–4: Capability truth gate ═══${NC}"
TRUTH_ARGS=""
if [ "$CI_MODE" = "true" ]; then
    TRUTH_ARGS="--ci"
fi
if python3 "$WORKSPACE/scripts/verify_capability_truth.py" $TRUTH_ARGS 2>&1; then
    echo -e "${GREEN}✅ capability truth gate 通过${NC}"
else
    echo -e "${RED}❌ capability truth gate 失败${NC}"
    echo "  修复: python3 scripts/verify_capability_truth.py --ci"
    echo "  矩阵: python3 scripts/generate_impact_matrix.py"
    echo "  路径: python3 scripts/verify_capability_doc.py --ci"
    VIOLATIONS=$((VIOLATIONS + 1))
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ "$VIOLATIONS" -eq 0 ]; then
    echo -e "${GREEN}═══ DOC SYNC PASSED — all checks clear ═══${NC}"
    exit 0
else
    echo -e "${RED}═══ DOC SYNC FAILED: $VIOLATIONS violation(s) ═══${NC}"
    echo ""
    echo "  修复方法:"
    echo "    1. 更新 AIPLAT_CAPABILITIES.md 添加新能力 / 修正路径"
    echo "    2. python3 scripts/generate_impact_matrix.py（若矩阵过期）"
    echo "    3. python3 scripts/verify_capability_truth.py --ci"
    echo "    4. 重新运行: bash scripts/verify_doc_sync.sh [--ci]"
    exit 1  # always block — doc sync is mandatory
fi
