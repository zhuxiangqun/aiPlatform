#!/bin/bash
# pre-commit — 快速预检：编译 + 文档同步
# 安装在: .git/hooks/pre-commit
# 跳过: git commit --no-verify

set -euo pipefail

WORKSPACE="$(git rev-parse --show-toplevel)"
PY="$(dirname "$(command -v python3)")/python3"

STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' | grep -v __pycache__ || true)

if [ -z "$STAGED_PY" ]; then
    exit 0  # no Python changes, skip
fi

echo ""
echo "=== pre-commit: $(echo "$STAGED_PY" | wc -l) staged .py files ==="

# ── Step 1: Compile check (fast, 1-2s) ──
FAILED=0
for f in $STAGED_PY; do
    if ! python3 -m py_compile "$WORKSPACE/$f" 2>/dev/null; then
        echo "  ❌ $f does not compile"
        FAILED=1
    fi
done
if [ "$FAILED" -eq 1 ]; then
    echo ""
    echo "  Aborting commit. Fix compilation errors first."
    exit 1
fi

# ── Step 1.5: Capability convergence guard (fast, ~2s) ──
if [ -f "$WORKSPACE/scripts/capability_guard.sh" ]; then
    if ! bash "$WORKSPACE/scripts/capability_guard.sh" 2>&1 | tail -3; then
        echo "  ⚠ Capability guard found issues (advisory only)"
    fi
fi

# ── Step 1.5: Ensure architecture guard rules are synced with boundary_rules.yaml ──
BOUNDARY_YAML="$WORKSPACE/architecture/boundary_rules.yaml"
GUARD_SCRIPT="$WORKSPACE/scripts/architecture_guard_rules.sh"
if [ -f "$BOUNDARY_YAML" ] && [ -f "$GUARD_SCRIPT" ]; then
    YAML_HASH=$(sha256sum "$BOUNDARY_YAML" | cut -d' ' -f1)
    GUARD_HASH=$(grep "SOURCE_HASH:" "$GUARD_SCRIPT" 2>/dev/null | awk '{print $NF}' || echo "")
    if [ "$YAML_HASH" != "$GUARD_HASH" ]; then
        echo ""
        echo "  ⚠ boundary_rules.yaml changed but architecture_guard_rules.sh not synced"
        echo "  Running generate_guard_rules.py..."
        if python3 "$WORKSPACE/scripts/generate_guard_rules.py" 2>/dev/null; then
            git add "$GUARD_SCRIPT" "$WORKSPACE/scripts/guard_patterns/" 2>/dev/null || true
            echo "  ✅ Guard rules auto-synced and staged"
        else
            echo "  ❌ Guard rules sync failed — run manually: python3 scripts/generate_guard_rules.py"
        fi
    fi
fi

# ── Step 1.75: Detect new router files in core/api/routers/ ──
# Per app-module-layout.md, new application modules must NOT add routes in core/api/routers/
NEW_CORE_ROUTERS=$(git diff --cached --name-only --diff-filter=A | grep 'aiPlat-core/core/api/routers/.*\.py$' | grep -v __pycache__ || true)
if [ -n "$NEW_CORE_ROUTERS" ]; then
    echo ""
    echo "  ⚠️  New router file detected in core/api/routers/:"
    echo "$NEW_CORE_ROUTERS" | while read f; do echo "    → $f"; done
    echo ""
    echo "  Per app-module-layout.md, new application modules must place routes in:"
    echo "  aiPlat-platform/apps/{module}/api/routers.py — NOT core/api/routers/"
    echo ""
    echo "  If this is a core capability router (not an app module), add:"
    echo "  # core-routing: allowed (describe why this is a core capability)"
    echo "  as a comment on line 1 of the file to suppress this warning."
fi

# ── Step 1.8: Detect new hardcoded business strings in harness ──
NEW_HARNESS_HARDCODES=$(git diff --cached -U0 | grep -E '^\+.*"[a-z]+-[a-z]+"' | grep -v '#\|__pycache__\|test_' || true)
if [ -n "$NEW_HARNESS_HARDCODES" ]; then
    echo ""
    echo "  ⚠️  New hardcoded domain-like strings detected in staged changes:"
    echo "$NEW_HARNESS_HARDCODES" | head -5
    echo "  Per CLAUDE.md §5.29, harness must be kernel-agnostic. Use DomainRouter instead."
    echo ""
fi

# ── Step 2: Auto-sync CAPABILITIES.md ──
CAPS_CHANGED=$(echo "$STAGED_PY" | grep -c "AIPLAT_CAPABILITIES.md\|AIPLAT_ROADMAP.md" || echo 0)
NONCAPS_CHANGED=$(echo "$STAGED_PY" | grep -cv "AIPLAT_CAPABILITIES.md\|AIPLAT_ROADMAP.md\|__pycache__" || echo 0)

if [ "$NONCAPS_CHANGED" -gt 0 ]; then
    echo ""
    echo "  Auto-syncing CAPABILITIES.md..."
    if bash "$WORKSPACE/scripts/auto_sync_docs.sh" 2>&1 | tail -5; then
        # Stage the auto-updated CAPABILITIES.md if it changed
        if [ -f "$WORKSPACE/AIPLAT_CAPABILITIES.md" ] && ! git diff --cached --quiet "$WORKSPACE/AIPLAT_CAPABILITIES.md" 2>/dev/null; then
            git add "$WORKSPACE/AIPLAT_CAPABILITIES.md" 2>/dev/null || true
            echo "  ✅ CAPABILITIES.md auto-synced and staged"
        fi
    else
        echo "  ⚠ Auto-sync had issues (manual review recommended)"
    fi
    # ── Auto-fix stats table (recalculate from actual section counts) ──
    if ! python3 "$WORKSPACE/scripts/verify_capability_consistency.py" --fix 2>/dev/null; then
        echo "  ❌ CAPABILITIES.md stats auto-fix failed — manual review required"
        echo "     Run: python3 scripts/verify_capability_consistency.py"
        exit 1
    fi
fi

# ── Step 3: 分流守卫 — 防止往 CLAUDE.md 新增状态型 §5.NNN (WARNING, 不阻断) ──
if echo "$STAGED_PY" | grep -q "CLAUDE.md" || git diff --cached --name-only | grep -q "aiPlat-core/CLAUDE.md"; then
    python3 "$WORKSPACE/scripts/guard_claude_status.py" --staged || true
fi

# ── Step 4: 接线完成度快速检查 (harness/management files only) ──
HARNESS_CHANGED=$(echo "$STAGED_PY" | grep -c "harness/\|management/\|infrastructure/\|execution/\|evaluation/\|coordination/\|memory/\|knowledge/\|syscalls/\|context/\|routing/\|learning/\|scheduler/\|training/\|monitoring/" || echo 0)
if [ "$HARNESS_CHANGED" -gt 0 ]; then
    echo ""
    echo "  Checking caller wiring for harness/management changes..."
    if bash "$WORKSPACE/scripts/method_verify.sh" --staged --quiet 2>&1; then
        echo "  ✅ Wiring check: all staged methods have callers"
    else
        echo "  ❌ Wiring check FAILED: dead methods detected"
        echo "     Run: bash scripts/method_verify.sh for details"
        exit 1
    fi
fi

# ── Step 5: 路由重复检测 (routers/*.py files only) ──
ROUTER_CHANGED=$(echo "$STAGED_PY" | grep -c "routers/" || echo 0)
if [ "$ROUTER_CHANGED" -gt 0 ]; then
    echo ""
    echo "  Checking route duplication for router changes..."
    ROUTE_DUPES=$(python3 -c "
import ast, os
from collections import Counter

routers_dir = '$WORKSPACE/aiPlat-core/core/api/routers'
duplicates = []

for fname in sorted(os.listdir(routers_dir)):
    if not fname.endswith('.py') or fname == '__init__.py':
        continue
    fpath = os.path.join(routers_dir, fname)
    try:
        tree = ast.parse(open(fpath).read(), filename=fpath)
    except Exception:
        continue

    prefix = ''
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and hasattr(node.func, 'attr'):
            if node.func.attr == 'APIRouter':
                for kw in node.keywords:
                    if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
            if (isinstance(node.func, ast.Attribute) and
                hasattr(node.func, 'value') and
                hasattr(node.func.value, 'id') and
                node.func.value.id == 'router' and
                node.func.attr in ('get', 'post', 'put', 'delete', 'patch')):
                if node.args and isinstance(node.args[0], ast.Constant):
                    routes.append((prefix + node.args[0].value, node.func.attr.upper()))

    for (p, m), c in Counter(routes).items():
        if c > 1:
            duplicates.append(f'{fname}: {m} {p} (x{c})')

if duplicates:
    for d in duplicates:
        print(f'    {d}')
" 2>/dev/null)
    if [ -n "$ROUTE_DUPES" ]; then
        echo "  ❌ Route duplicates detected:"
        echo "$ROUTE_DUPES"
        echo "     Fix duplicate @router paths before committing."
        exit 1
    else
        echo "  ✅ No route duplicates detected"
    fi
fi

echo "  ✓ pre-commit checks passed"
echo ""
exit 0
