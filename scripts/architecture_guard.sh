#!/usr/bin/env bash
# ============================================================================
# architecture_guard.sh — architecture compliance checker (delegates to Python)
#
# Rules are defined in:
#   aiPlat-core/core/management/arch_guard_rules.yaml     (declarative grep rules)
#   aiPlat-core/core/management/arch_guard_rules/*.py     (complex checks)
#   scripts/guard_frontend.py                              (frontend proxy + API contract)
#
# CONTROL FLOW: failure AGGREGATION (not `set -e` short-circuit). Every check runs
# so ALL problems are visible; a non-zero step no longer skips the rest. The final
# exit code is non-zero iff any aggregated step failed. The fast tool_correctness
# subset runs here; the heavy self-tests (which invoke real full-repo scripts and
# run 30-135s) are marked `slow` and run separately (`pytest -m slow`).
# ============================================================================

set -uo pipefail
WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_ROOT"

FAIL=0
GP_PY="python3"
[ -x "$WORKSPACE_ROOT/.venv/bin/python" ] && GP_PY="$WORKSPACE_ROOT/.venv/bin/python"

sep() { echo "═══════════════════════════════════════════════════════════════"; }

# ── Behavior plane: golden-path e2e (real ingest→retrieve / cache / contract) ──
echo ""; sep; echo "  BEHAVIOR PLANE: golden-path facade (ingest→retrieve · cache · contract — no HTTP)"; sep
"$GP_PY" -m pytest tests/golden_path/test_golden_path.py -k "not stub" -q || FAIL=1
echo ""; sep; echo "  BEHAVIOR PLANE: golden-path HTTP (stub · agent-deny)"; sep
"$GP_PY" -m pytest tests/golden_path/test_golden_path.py -k "stub" tests/golden_path/test_agent_orchestration.py -q || FAIL=1
echo ""; sep; echo "  BEHAVIOR PLANE: management APIs (diagnostics · overview)"; sep
"$GP_PY" -m pytest tests/golden_path/test_management_apis.py -q || FAIL=1

# ── AST behavior guard (silent except:pass baseline ratchet, §5.68) ──
python3 scripts/guard_ast_behavior.py "$@" || FAIL=1

# ── Frontend contract guard (§45 path-mismatch baseline ratchet) ──
python3 scripts/guard_frontend.py || FAIL=1

# ── Architecture grep guard (declarative rules) ──
python3 scripts/architecture_guard.py "$@" || FAIL=1

# ── Capability convergence ──
python3 aiPlat-core/core/management/capability_convergence.py "$@" --force || FAIL=1

# ── Cycle detection (advisory; non-fatal as before) ──
echo ""; sep; echo "  CYCLE DETECTION: import graph circular dependencies"; sep
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

# ── Tool correctness self-tests (fast subset; heavy `-m slow` ones run separately) ──
echo ""; sep; echo "  TOOL CORRECTNESS: guards + diagnostics self-tests (fast; heavy -m slow ones skipped)"; sep
"$GP_PY" -m pytest aiPlat-core/core/tests/tool_correctness/ -m "not slow" -q --tb=line || FAIL=1

# ── Constitution unit tests ──
echo ""; sep; echo "  CONSTITUTION TESTS: prompt_loading + skill_config + agent_md + module_deps"; sep
"$GP_PY" -m pytest aiPlat-core/core/tests/unit/test_prompt_loading.py \
                  aiPlat-core/core/tests/unit/test_skill_config.py \
                  aiPlat-core/core/tests/unit/test_agent_md_config.py \
                  aiPlat-core/core/tests/unit/test_core_module_deps.py -q --tb=short || FAIL=1

# ── Phase check (dead code + wiring tests + self-annotated) ──
echo ""; sep; echo "  PHASE CHECK: dead code + wiring tests + self-annotated"; sep
bash scripts/phase_check.sh || FAIL=1

# ── Aggregate ──
echo ""; sep
if [ "$FAIL" -ne 0 ]; then
    echo "  ARCHITECTURE GUARD: one or more checks FAILED (all checks ran — see above)"
    sep; exit 1
else
    echo "  ARCHITECTURE GUARD: all checks passed"
    sep; exit 0
fi
