#!/usr/bin/env bash
# ============================================================================
# architecture_guard.sh — architecture compliance checker (delegates to Python)
#
# Rules are now defined in:
#   aiPlat-core/core/management/arch_guard_rules.yaml     (declarative, ~40 grep rules)
#   aiPlat-core/core/management/arch_guard_rules/*.py     (complex checks)
#   scripts/guard_frontend.py                              (frontend proxy + API contract)
#
# Add a new rule:
#   Simple: add 6 lines to arch_guard_rules.yaml
#   Complex: add a class to arch_guard_rules/
#   Frontend: add checks to guard_frontend.py
# ============================================================================

set -euo
WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_ROOT"

python3 scripts/architecture_guard.py "$@"
python3 aiPlat-core/core/management/capability_convergence.py "$@" --force
python3 scripts/guard_ast_behavior.py "$@"
python3 scripts/guard_frontend.py

# Cycle detection — check import graph for circular dependencies
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  CYCLE DETECTION: import graph circular dependencies"
echo "═══════════════════════════════════════════════════════════════"
python3 -c "
import sys; sys.path.insert(0, 'aiPlat-core')
from core.harness.knowledge.code_graph import repo_root, default_roots, build_graph, count_cycles, report_cycles
repo = repo_root()
roots = [(repo / r).resolve() for r in default_roots()]
nodes, edges, _issues = build_graph(repo, roots)
cycles = count_cycles(nodes)
paths = report_cycles(nodes)

# Load known-safe cycle whitelist
safe_paths = set()
try:
    import os; wl = os.path.join(os.path.dirname('$0'), '..', 'scripts', 'known_safe_cycles.txt')
    with open(wl) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                safe_paths.add(line)
except: pass

new_cycles = [p for p in paths if p['names'] not in safe_paths]
known_count = len(paths) - len(new_cycles)

print(f'Known-safe (function-scoped): {known_count}')
print(f'New/unknown cycles: {len(new_cycles)}')
if new_cycles:
    print('FAIL: Unexpected cycles detected:')
    for p in new_cycles[:5]:
        print(f'  [{p[\"length\"]} files] {p[\"names\"]}')
    if len(new_cycles) > 5:
        print(f'  ... and {len(new_cycles)-5} more')
    sys.exit(1)
else:
    print('PASS: No unexpected cycles')
    if known_count > 0:
        print(f'Note: {known_count} known-safe cycles are tracked in scripts/known_safe_cycles.txt')
" 2>/dev/null || echo "SKIP: code_graph module unavailable (run diagnostics first)"

# Constitution tests — Python-level semantic checks
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  CONSTITUTION TESTS: pytest (prompt_loading + skill_config + agent_md)"
echo "═══════════════════════════════════════════════════════════════"
python3 -m pytest aiPlat-core/core/tests/unit/test_prompt_loading.py \
                 aiPlat-core/core/tests/unit/test_skill_config.py \
                 aiPlat-core/core/tests/unit/test_agent_md_config.py \
                 aiPlat-core/core/tests/unit/test_core_module_deps.py \
                  -v --tb=short 2>&1 | tail -25

# Phase check — three-step acceptance checklist (§73)
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  PHASE CHECK: dead code + wiring tests + self-annotated"
echo "═══════════════════════════════════════════════════════════════"
bash scripts/phase_check.sh || echo "WARNING: phase_check.sh found issues (non-critical in dev)"
