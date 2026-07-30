#!/usr/bin/env bash
# ============================================================================
# caller_verify.sh — 接线完成度验证脚本
#
# 扫描全仓关键模块的公共符号，检测 0 调用者的死代码。
# 覆盖范围：harness 核心 + Phase 0-6 全部新增模块
#
# Usage: bash scripts/caller_verify.sh
# ============================================================================
set -euo

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
# Build one-time inverted index: which symbols appear in which files
# ------------------------------------------------------------------
_log "  Building symbol index (one-pass scan)..."
ALL_FILES=$(find "$WORKSPACE/aiPlat-core" "$WORKSPACE/aiPlat-platform" "$WORKSPACE/aiPlat-app" \
    -name '*.py' -not -path '*/__pycache__/*' -not -path '*/tests/*' \
    -not -name 'conftest.py' 2>/dev/null)

# Pre-index: for each file, extract all tokens and write file_path:token
INDEX_FILE="$TMPDIR/symbol_index.txt"
total=$(echo "$ALL_FILES" | wc -l | tr -d ' ')
i=0
while IFS= read -r f; do
    [ -z "$f" ] && continue
    # Extract words (identifiers) — cheap tokenization
    tr -c 'A-Za-z0-9_' '\n' < "$f" 2>/dev/null | sort -u 2>/dev/null | while read -r token; do
        [ ${#token} -ge 3 ] && echo "$token|$f"
    done || true  # prevent pipefail crash on header-only files
    i=$((i + 1))
    [ $((i % 50)) -eq 0 ] && echo -ne "\r    indexed $i/$total files..." >&2
done <<< "$ALL_FILES" > "$INDEX_FILE"
echo -e "\r    indexed $total files done.      " >&2

# Look up symbol in index: count distinct caller files (excluding self + tests)
lookup_callers() {
    local symbol="$1"
    local self_basename="$2"
    local hits
    hits=$(grep "^$symbol|" "$INDEX_FILE" 2>/dev/null \
        | cut -d'|' -f2 \
        | grep -v "$self_basename" \
        | grep -v '/tests/' \
        | grep -v '/diagnostics' \
        | grep -v '/management/arch_guard' \
        | sort -u \
        | wc -l | tr -d ' ')
    [ "${hits:-0}" -gt 0 ]
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

# ===================================================================
# Check: key harness files for dead public symbols
# ===================================================================
HARNESS_DIR="$WORKSPACE/aiPlat-core/core/harness"
CORE_DIR="$WORKSPACE/aiPlat-core/core"

PRIORITY_FILES=(
    # ── Harness core infrastructure ──
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
    # ── Phase 0: 紧急止血 ──
    "CORE_SERVICES:pii_detector.py"
    "knowledge/semantic_cache.py"
    # ── Phase 1: 铸造利刃 ──
    "CORE_APPS:apps/agents/parallel_executor.py"
    # ── Phase 2: 自进化大脑 ──
    "knowledge/provenance.py"
    "learning/__init__.py"
    "learning/skill_simulator.py"
    "CORE_GATEWAY:gateway/__init__.py"
    # ── Phase 3: 前沿能力 ──
    "evaluation/hallucination_tracker.py"
    "deployment/canary.py"
    # ── Phase 4: 自进化闭环 ──
    "infrastructure/hooks/on_error_reflector.py"
    "CORE_SERVICES:implicit_feedback.py"
    "training/auto_trigger.py"
    "meta/__init__.py"
    # ── Phase 5: 软隐空间 ──
    "learning/experience_vector.py"
    "execution/pattern_cache.py"
    "evolution_engine.py"
    # ── Phase 6: 安全审计 ──
    "security/code_auditor.py"
)

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Caller Verification — Dead Code Detection"
echo "  Coverage: ${#PRIORITY_FILES[@]} key modules"
echo "═══════════════════════════════════════════════════════════════"
echo ""

for entry in "${PRIORITY_FILES[@]}"; do
    # Support prefix redirection: CORE_SERVICES:file.py → core/services/file.py
    f=""
    if [[ "$entry" == CORE_SERVICES:* ]]; then
        f="$CORE_DIR/services/${entry#CORE_SERVICES:}"
    elif [[ "$entry" == CORE_APPS:* ]]; then
        f="$CORE_DIR/${entry#CORE_APPS:}"
    elif [[ "$entry" == CORE_GATEWAY:* ]]; then
        f="$CORE_DIR/${entry#CORE_GATEWAY:}"
    elif [[ "$entry" == CORE_HARNESS:* ]]; then
        f="$HARNESS_DIR/${entry#CORE_HARNESS:}"
    else
        f="$HARNESS_DIR/$entry"
    fi
    [ -f "$f" ] || continue
    basename_f="$(basename "$f")"

    while IFS= read -r name; do
        [ -z "$name" ] && continue
        if ! lookup_callers "$name" "$basename_f"; then
            rel="${entry#CORE_*:}"
            _log "  ${RED}→${NC} $rel: $name — ${RED}0 callers${NC}"
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
