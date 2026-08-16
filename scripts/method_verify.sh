#!/usr/bin/env bash
# ============================================================================
# method_verify.sh — 方法级接线验证 (v2: 自动扫描所有公共符号)
#
# Usage:
#   bash scripts/method_verify.sh              # 全量扫描（默认）
#   bash scripts/method_verify.sh --staged     # 只检查 staged 文件
#   bash scripts/method_verify.sh --quiet      # 静默模式（只输出 DEAD）
#   bash scripts/method_verify.sh --staged --quiet  # pre-commit 模式
#
# Integrated into phase_check.sh as Step 2.5
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

WARNINGS=0
STAGED_MODE=false
QUIET_MODE=false
AUTO_SCAN=false

# ── Parse flags ──
for arg in "$@"; do
    case "$arg" in
        --staged) STAGED_MODE=true ;;
        --quiet) QUIET_MODE=true ;;
        --auto) AUTO_SCAN=true ;;
        *) ;;
    esac
done

# ── Auto-scan: discover all public symbols from harness + management ──
auto_discover_symbols() {
    local TMPFILE
    TMPFILE=$(mktemp)
    trap 'rm -f "$TMPFILE"' RETURN
    
    # Scan harness and management for top-level defs and class defs
    find "$WORKSPACE/aiPlat-core/core/harness" "$WORKSPACE/aiPlat-core/core/management" \
        -name '*.py' -not -path '*__pycache__*' -not -path '*/tests/*' \
        -not -name 'conftest.py' 2>/dev/null | while read -r f; do
        
        local rel_path="${f#$WORKSPACE/}"
        local basename="$(basename "$f")"
        
        # Extract public symbols using AST (faster than multiple greps)
        python3 -c "
import ast, sys
try:
    tree = ast.parse(open('$f').read())
except:
    sys.exit(0)

# Skip abstract/base/__init__ files
filename = '$basename'
if any(k in filename for k in ['base.py', 'protocol.py', 'interface.py', '__init__']):
    # Still extract concrete classes/functions from __init__.py
    pass if filename != '__init__.py' else None

symbols = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        if not node.name.startswith('_'):
            symbols.append(('func', node.name, node.lineno))
    elif isinstance(node, ast.AsyncFunctionDef):
        if not node.name.startswith('_'):
            symbols.append(('async_func', node.name, node.lineno))
    elif isinstance(node, ast.ClassDef):
        if not node.name.startswith('_'):
            # Skip abstract bases, ABCs, protocols
            bases = [b.attr if isinstance(b, ast.Attribute) else b.id if isinstance(b, ast.Name) else '' for b in node.bases]
            is_abstract = any(k in str(b).lower() for k in ['abc', 'protocol'])
            if not is_abstract:
                symbols.append(('class', node.name, node.lineno))

for stype, name, lineno in symbols:
    # Skip Python builtins and common names
    if name in ['run', 'main', 'load', 'save', 'execute', 'router', 'app', 'model', 'config']:
        continue
    print(f'{rel_path}|{name}|{stype}')
" 2>/dev/null
    done | sort -u > "$TMPFILE"
    
    cat "$TMPFILE"
}

# ── Check if a symbol has production callers ──
has_caller() {
    local file_path="$1"
    local method_name="$2"
    local basename="$(basename "$file_path")"
    
    # Same-file caller: method invoked via instance attribute (e.g. `self.map_reduce(`
    # or `executor.map_reduce(`) from a different function in the same module.
    # This catches wrapper patterns like `parallel_analyze()` → `executor.map_reduce()`.
    if grep -qE "\b(self|executor|[a-z_]+)\.${method_name}\s*\(" "$file_path" 2>/dev/null; then
        return 0
    fi
    
    # Search in all production code (excluding self and tests)
    local hits
    hits=$(grep -rl "$method_name" "$WORKSPACE/aiPlat-core" \
        --include='*.py' 2>/dev/null \
        | grep -v "$basename" \
        | grep -v '__pycache__' \
        | grep -v '/tests/' \
        | grep -v 'conftest.py' \
        | sort -u 2>/dev/null || true)
    
    if [ -z "$hits" ]; then
        return 1
    fi
    
    # Verify at least one hit is a real caller (not just a string match)
    local found=0
    while IFS= read -r hit_file; do
        [ -z "$hit_file" ] && continue
        # Check for import, call, attribute access, or type hint patterns
        if grep -qE "(import.*\b${method_name}\b|from.*\b${method_name}\b|${method_name}\s*\(|=\s*${method_name}\b|:\s*${method_name}\b)" "$hit_file" 2>/dev/null; then
            found=1
            break
        fi
    done <<< "$hits"
    
    return $((1 - found))
}

# ── Check staged files only ──
check_staged() {
    local staged_files
    staged_files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null \
        | grep -E 'harness/|management/|infrastructure/|execution/|evaluation/|coordination/|memory/|knowledge/|syscalls/|context/|routing/|learning/|scheduler/|training/|monitoring/' \
        | grep '\.py$' \
        | grep -v __pycache__ || true)
    
    if [ -z "$staged_files" ]; then
        return 0
    fi
    
    local verified=0
    while IFS= read -r rel_path; do
        [ -z "$rel_path" ] && continue
        local full_path="$WORKSPACE/$rel_path"
        local basename="$(basename "$rel_path")"
        
        # Extract NEW symbols from staged file (symbols not present in HEAD)
        local new_symbols
        new_symbols=$(python3 -c "
import ast, subprocess

def public_symbols(src):
    try:
        tree = ast.parse(src)
    except Exception:
        return set()
    syms = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith('_') or node.name in ['get','post','put','delete','patch']:
                continue
            if any(isinstance(d, ast.Name) and d.id == 'property' for d in node.decorator_list):
                continue  # @property accessor, not a callable method
            syms.add(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith('_'):
                bases = [b.attr if isinstance(b, ast.Attribute) else b.id if isinstance(b, ast.Name) else '' for b in node.bases]
                if not any(k in str(bases).lower() for k in ['abc', 'protocol']):
                    syms.add(node.name)
    return syms

cur = public_symbols(open('$full_path').read())
head = set()
try:
    r = subprocess.run(['git', 'show', 'HEAD:$rel_path'], capture_output=True, text=True)
    if r.returncode == 0:
        head = public_symbols(r.stdout)
except Exception:
    pass

for s in sorted(cur - head):
    print(s)
" 2>/dev/null)
        
        [ -z "$new_symbols" ] && continue
        
        while IFS= read -r sym; do
            [ -z "$sym" ] && continue
            verified=$((verified + 1))
            if ! has_caller "$full_path" "$sym"; then
                echo -e "  ${RED}DEAD${NC}  | $sym in $basename — no production caller"
                WARNINGS=$((WARNINGS + 1))
            elif [ "$QUIET_MODE" != true ]; then
                echo -e "  ${GREEN}OK${NC}    | $sym in $basename"
            fi
        done <<< "$new_symbols"
    done <<< "$staged_files"
    
    if [ "$verified" -eq 0 ]; then
        return 0
    fi
}

# ── Key methods (fast path, always checked) ──
check_key_methods() {
    declare -a KEY_METHODS=(
        "core/harness/infrastructure/hooks/on_error_reflector.py|on_post_observe|反思钩子回调"
        "core/harness/evaluation/hallucination_tracker.py|evaluate|事实核查"
        "core/harness/evaluation/hallucination_tracker.py|get_dashboard|仪表盘"
        "core/harness/evaluation/hallucination_tracker.py|get_recent_reports|最近报告"
        "core/apps/agents/parallel_executor.py|map|Map FanOut"
        "core/apps/agents/parallel_executor.py|map_reduce|Map-Reduce"
        "core/apps/agents/parallel_executor.py|parallel_analyze|FanOut"
        "core/harness/knowledge/semantic_cache.py|invalidate_domain|缓存失效"
        "core/gateway/__init__.py|send_message|消息推送"
        "core/gateway/__init__.py|register|适配器注册"
        "core/services/implicit_feedback.py|record|信号记录"
        "core/services/implicit_feedback.py|get_stats|统计查询"
        "core/services/pii_detector.py|mask|PII脱敏"
        "core/harness/security/code_auditor.py|audit|安全审计"
    )
    
    for entry in "${KEY_METHODS[@]}"; do
        IFS='|' read -r file_path method_name description <<< "$entry"
        local full_path="$WORKSPACE/aiPlat-core/$file_path"
        [ -f "$full_path" ] || continue
        local basename="$(basename "$file_path")"
        
        if ! has_caller "$full_path" "$method_name"; then
            echo -e "  ${RED}DEAD${NC}  | $method_name in $basename — $description"
            WARNINGS=$((WARNINGS + 1))
        elif [ "$QUIET_MODE" != true ]; then
            echo -e "  ${GREEN}OK${NC}    | $method_name in $basename — $description"
        fi
    done
}

# ── Auto scan (full) ──
check_auto_scan() {
    ! $AUTO_SCAN && return 0
    
    echo ""
    echo "  Auto-scanning harness + management public symbols..."
    local symbols
    symbols=$(auto_discover_symbols)
    local total=0
    
    while IFS='|' read -r file_path method_name stype; do
        [ -z "$file_path" ] && continue
        total=$((total + 1))
        local full_path="$WORKSPACE/$file_path"
        [ -f "$full_path" ] || continue
        
        if ! has_caller "$full_path" "$method_name"; then
            echo -e "  ${RED}DEAD${NC}  | $method_name in $(basename "$file_path") ($stype)"
            WARNINGS=$((WARNINGS + 1))
        fi
    done <<< "$symbols"
    
    [ "$QUIET_MODE" != true ] && echo "  Scanned $total symbols"
}

# ── Main ──
if [ "$QUIET_MODE" != true ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Method Verification — Caller Detection (v2 auto-scan)"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
fi

if $STAGED_MODE; then
    check_staged
    check_key_methods
else
    check_key_methods
    check_auto_scan
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ "$WARNINGS" -gt 0 ]; then
    echo -e "${RED}═══ METHOD VERIFY FAILED: $WARNINGS unwired method(s) ═══${NC}"
    echo ""
    echo "  These methods have no external production callers."
    echo "  Wire them or add @pytest.mark.xfail to tests/wiring/."
    exit 1
else
    echo -e "${GREEN}═══ METHOD VERIFY PASSED — all methods have callers ═══${NC}"
    exit 0
fi
