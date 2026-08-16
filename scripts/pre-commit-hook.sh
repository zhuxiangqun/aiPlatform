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

# ── Step 2.5: Doc sync enforcement (code_doc_map.yaml) ──
echo ""
bash "$WORKSPACE/scripts/verify_doc_sync.sh" --ci || {
  echo "❌ 文档同步检查失败 — 请在 commit message 中标注 doc-sync 或更新对应文档"
  exit 1
}

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

# ── Step 6: Architecture guard (quick) — catch new violations before commit ──
echo ""
echo "  Running architecture guard (quick)..."
if ! bash "$WORKSPACE/scripts/architecture_guard.sh" --quick 2>&1; then
    echo ""
    echo "  ❌ Architecture guard found violations. Fix before committing."
    exit 1
fi

echo "  ✓ pre-commit checks passed"
echo ""
exit 0

# ── Step 1.9: Detect new routes missing response_model ──
NEW_ROUTES_WITHOUT_MODEL=$(git diff --cached -U0 | grep -E '^\+.*@router\.(get|post|put|delete)' | grep -v "response_model" | grep -v "#\|__pycache__" || true)
if [ -n "$NEW_ROUTES_WITHOUT_MODEL" ]; then
    echo ""
    echo "  ⚠️  New route(s) added without response_model:"
    echo "$NEW_ROUTES_WITHOUT_MODEL" | head -5 | while read line; do echo "    $line"; done
    echo "  Per §5.76, add response_model=Dict[str, Any] or specific Pydantic model."
    echo ""
fi

# ── Phase 42: Verify capability count consistency ──
if [ -z "${SKIP_CAPABILITY_CHECK:-}" ]; then
    bash "$WORKSPACE/scripts/verify_capability_counts.sh" || {
        echo "  ❌ Capability count drift detected. Fix hardcoded numbers or run:"
        echo "     bash scripts/verify_capability_counts.sh"
        exit 1
    }
    echo "  ✅ Capability counts consistent"
fi

# ── Phase 43: Capability-to-consumer traceability ──
if [ -z "${SKIP_CAPABILITY_CONSUMERS:-}" ]; then
    bash "$WORKSPACE/scripts/verify_capability_consumers.sh" || {
        echo "  ⚠️  Capability consumer warnings (review before pushing)"
        echo "     Set BLOCK_CAPABILITY_GAP=1 to block commits on gap detection"
    }
fi

# ── Phase 43: Capability auto-registration check ──
if [ -z "${SKIP_CAP_REGISTRATION:-}" ]; then
    bash "$WORKSPACE/scripts/cap" check || {
        echo ""
        echo "  ❌ Unregistered capabilities detected."
        echo "  → Run: cap auto-register"
        echo "  → Fill in the TODO fields in each draft"
        echo "  → Stage the updated registry: git add $WORKSPACE/aiPlat-core/core/capability_registry.yaml"
        echo "  → Commit again."
        echo ""
        echo "  (Set SKIP_CAP_REGISTRATION=1 to bypass, not recommended)"
        exit 1
    }
    echo "  ✅ All capabilities registered"
fi

# ── Phase 46: Entity registration guard (agent_type, API key, directory whitelist) ──
if [ -z "${SKIP_ENTITY_GUARD:-}" ]; then
    ENTITY_ISSUES=0

    # P1: 禁止 os.getenv("DEEPSEEK_API_KEY") — 必须走 get_llm_api_key()
    if echo "$STAGED_PY" | xargs grep -l 'os\.getenv.*DEEPSEEK_API_KEY\|os\.getenv.*AIPLAT_LLM_API_KEY' 2>/dev/null | grep -v 'llm_env.py\|model_injection.py\|infra' > /tmp/precommit_apikey.txt; then
        echo "  ❌ Direct os.getenv(API_KEY) detected in staged files:"
        cat /tmp/precommit_apikey.txt | sed 's/^/     /'
        echo "     → Use get_llm_api_key() from core.harness.utils.llm_env instead"
        ENTITY_ISSUES=1
    fi

    # P2: AGENT.md 目录白名单 — 只允许 engine/agents/ 和 ~/.aiplat/agents/
    NEW_AGENTS=$(git diff --cached --name-only --diff-filter=A | grep 'AGENT\.md$' || true)
    for f in $NEW_AGENTS; do
        if ! echo "$f" | grep -qE '(engine/agents/|\.aiplat/agents/)'; then
            echo "  ❌ New AGENT.md outside allowed directories: $f"
            echo "     → Allowed: core/engine/agents/ or ~/.aiplat/agents/"
            ENTITY_ISSUES=1
        fi
    done

    # P3: SKILL.md 目录白名单
    NEW_SKILLS=$(git diff --cached --name-only --diff-filter=A | grep 'SKILL\.md$' || true)
    for f in $NEW_SKILLS; do
        if ! echo "$f" | grep -qE '(engine/skills/|\.aiplat/skills/)'; then
            echo "  ❌ New SKILL.md outside allowed directories: $f"
            echo "     → Allowed: core/engine/skills/ or ~/.aiplat/skills/"
            ENTITY_ISSUES=1
        fi
    done

    # P4: 禁止新增 response_model=dict
    if echo "$STAGED_PY" | xargs grep -l 'response_model=dict\b' 2>/dev/null | grep -v '# noqa: legacy-response-model' > /tmp/precommit_dict.txt; then
        echo "  ⚠️  New response_model=dict detected (advisory):"
        cat /tmp/precommit_dict.txt | sed 's/^/     /'
        echo "     → Use typed Pydantic response_model instead of dict"
    fi

    if [ "$ENTITY_ISSUES" -eq 1 ]; then
        echo ""
        echo "  ❌ Entity registration violations detected."
        echo "  → Set SKIP_ENTITY_GUARD=1 to bypass (not recommended)"
        exit 1
    fi
    echo "  ✅ Entity registration guard passed"
fi

# ── Phase 45: Architecture pattern compliance ──
if [ -z "${SKIP_ARCH_PATTERNS:-}" ]; then
    bash "$WORKSPACE/scripts/verify_architecture_patterns.sh" || {
        echo "  ⚠️  Architecture pattern warnings (review before pushing)"
        echo "     Set BLOCK_ARCH_PATTERNS=1 to block commits on pattern violations"
    }
fi

# ── Phase 47: CoreFacade signature ripple (only when core_facade.py changed) ──
if echo "$STAGED_PY" | grep -q 'core_facade.py' 2>/dev/null; then
    if ! python3 "$WORKSPACE/scripts/check_signature_ripple.py" --check 2>/dev/null; then
        echo "  ❌ CoreFacade signature changed — verify platform callers are updated"
        echo "     Run: python3 scripts/check_signature_ripple.py --check"
        echo "     Fix callers, then: python3 scripts/check_signature_ripple.py --update"
        FAIL=1
    fi
fi
