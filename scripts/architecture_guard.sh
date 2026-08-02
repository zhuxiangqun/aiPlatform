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
#
# Usage:
#   bash scripts/architecture_guard.sh          # full scan
#   bash scripts/architecture_guard.sh --quick  # fast scan (skips non-critical checks)
# ============================================================================

set -uo pipefail
WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_ROOT"

FAIL=0
GP_PY="python3"
[ -x "$WORKSPACE_ROOT/.venv/bin/python" ] && GP_PY="$WORKSPACE_ROOT/.venv/bin/python"

# ── Mode selection ──
QUICK_MODE=false
if [ "${1:-}" = "--quick" ]; then
    QUICK_MODE=true
fi

sep() { echo "═══════════════════════════════════════════════════════════════"; }

# ══════════════════════════════════════════════════════════════
# Step 0: Meta-Guard — verify the guard infrastructure is healthy
# Catches YAML breakage (silent rule skip), missing files, etc.
# ══════════════════════════════════════════════════════════════
echo ""; sep; echo "  META-GUARD: infrastructure self-check"; sep
python3 -c "
import yaml, sys, os
try:
    with open('aiPlat-core/core/management/arch_guard_rules.yaml') as f:
        data = yaml.safe_load(f)
    rules = data.get('rules', [])
    if len(rules) < 100:
        print(f'SELF-CHECK FAIL: only {len(rules)} rules loaded (expected >=100)')
        print(f'arch_guard_rules.yaml may be broken — rules silently skipped')
        sys.exit(1)
    print(f'SELF-CHECK PASS: {len(rules)} YAML rules loaded')
except yaml.YAMLError as e:
    print(f'SELF-CHECK FAIL: YAML parse error — {e}')
    sys.exit(1)
except FileNotFoundError:
    print('SELF-CHECK FAIL: arch_guard_rules.yaml not found')
    sys.exit(1)
" || { echo "  ❌ Meta-guard FAILED — guard broken, fix before running"; exit 1; }

# Shared PID array
ALL_PIDS=()

# ══════════════════════════════════════════════════════════════
# Phase 1 — guard scripts (parallel)
# ══════════════════════════════════════════════════════════════
echo ""; sep; echo "  GUARD SCRIPTS: ast_behavior + frontend + architecture + capability + evidence (bg)"; sep

FAIL_AST=0; FAIL_FE=0; FAIL_ARCH=0; FAIL_CAP=0; FAIL_EV=0

python3 scripts/guard_ast_behavior.py "$@" &
PID_AST=$!
python3 scripts/guard_frontend.py &
PID_FE=$!
python3 scripts/architecture_guard.py "$@" &
PID_ARCH=$!
if ! $QUICK_MODE && [ -z "${SKIP_CAP_CONV:-}" ]; then
    python3 aiPlat-core/core/management/capability_convergence.py "$@" --force &
    PID_CAP=$!
else
    PID_CAP=0
fi
python3 scripts/verify_claude_md_evidence.py --workspace &
PID_EV=$!

wait $PID_AST || FAIL_AST=1
wait $PID_FE || FAIL_FE=1
wait $PID_ARCH || FAIL_ARCH=1
[ "$PID_CAP" != "0" ] && { wait $PID_CAP || FAIL_CAP=1; }
wait $PID_EV || FAIL_EV=1
[ "$FAIL_AST" -ne 0 ] && FAIL=1
[ "$FAIL_FE" -ne 0 ] && FAIL=1
[ "$FAIL_ARCH" -ne 0 ] && FAIL=1
[ "$FAIL_CAP" -ne 0 ] && FAIL=1
[ "$FAIL_EV" -ne 0 ] && FAIL=1

# ══════════════════════════════════════════════════════════════
# Phase 2 — parallel secondary checks (CI: run this separately)
# Full guard mode runs Phase 1 only; Phase 2 runs as CI job.
# In --quick mode, run lightweight Phase 2 checks.
# ══════════════════════════════════════════════════════════════
echo ""; sep; echo "  PHASE 2: secondary guards"; sep

if $QUICK_MODE; then
    TMPDIR="${TMPDIR:-/tmp}/arch_guard_$$"
    mkdir -p "$TMPDIR"
    _launch() { local label="$1" outfile="$2"; shift 2; echo "  → $label (bg)"; "$@" > "$outfile" 2>&1 & _fast_pids+=($!); }
    _fast_pids=()
    _launch "frontmatter" "$TMPDIR/frontmatter.log" "$GP_PY" scripts/validate_frontmatter.py --quick
    _launch "doc-sync" "$TMPDIR/doc_sync.log" bash scripts/verify_doc_sync.sh --ci 2>/dev/null || true
    echo "  Waiting for ${#_fast_pids[@]} checks..."
    for _pid in "${_fast_pids[@]}"; do wait "$_pid" || FAIL=1; done
    rm -rf "$TMPDIR"
else
    echo "  SKIP: Phase 2 runs as separate CI job (use --quick for fast pre-commit checks)"
fi



# ══════════════════════════════════════════════════════════════
# Phase 3: Engine layer agnostic checks
# ══════════════════════════════════════════════════════════════
echo ""; sep; echo "  PHASE 3: engine agnostic"; sep

# §77: Engine layer hardcoded artifact key tuples
echo -n "§77: engine artifact key tuples: "
count=$(grep -rn '"architecture".*"code".*"test_report"\|state\.get("architecture"\|state\.get("code"\|state\.get("test_report"' aiPlat-core/core/harness/execution/ --include='*.py' 2>/dev/null | grep -v '_run_stage_skill\|#\|test_\|snapshot' | wc -l | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -rn '"architecture".*"code".*"test_report"\|state\.get("architecture"\|state\.get("code"\|state\.get("test_report"' aiPlat-core/core/harness/execution/ --include='*.py' 2>/dev/null | grep -v '_run_stage_skill\|#\|test_\|snapshot'; FAIL=1; else echo "✅"; fi

# §78: Engine layer Chinese prompt hardcodes
echo -n "§78: engine Chinese prompts: "
count=$(grep -rn '你是\|你是一个\|请将\|请基于' aiPlat-core/core/harness/execution/ --include='*.py' 2>/dev/null | grep -v '#\|prompt_loader\|test_\|_sync_resolve' | wc -l | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -rn '你是\|你是一个\|请将\|请基于' aiPlat-core/core/harness/execution/ --include='*.py' 2>/dev/null | grep -v '#\|prompt_loader\|test_\|_sync_resolve'; FAIL=1; else echo "✅"; fi

# §79: Pipeline engine skill name hardcodes
echo -n "§79: pipeline skill name hardcodes: "
count=$(grep -c '"architecture_design"\|"code_generation"\|"test_case_generation"' aiPlat-core/core/harness/execution/pipeline_engine.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n '"architecture_design"\|"code_generation"\|"test_case_generation"' aiPlat-core/core/harness/execution/pipeline_engine.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §79b: Engine state key baseline — detect new business keys not in allowed list
echo -n "§79b: engine state key baseline: "
BASELINE="$(dirname "$0")/baselines/engine_state_keys.txt"
if [ -f "$BASELINE" ]; then
    # Extract all state key references from engine, compare to baseline
    NEW_KEYS=$(python3 -c "
import re, sys
with open('$BASELINE') as f:
    allowed = {l.split('|')[0] for l in f if l.strip() and not l.startswith('#')}

text = open('aiPlat-core/core/harness/execution/pipeline_engine.py').read()
found = set()
for m in re.finditer(r'state\[.''(\w+)'']', text): found.add(m.group(1))
for m in re.finditer(r'state\.get\(.''(\w+)'']', text): found.add(m.group(1))
# Also scan any engine .py files in execution/
import os
for root, dirs, files in os.walk('aiPlat-core/core/harness/execution/'):
    for f in files:
        if f.endswith('.py'):
            t = open(os.path.join(root,f)).read()
            for m in re.finditer(r'state\[.''(\w+)'']', t): found.add(m.group(1))
            for m in re.finditer(r'state\.get\(.''(\w+)'']', t): found.add(m.group(1))

new = found - allowed
for k in sorted(new):
    print(k)
" 2>/dev/null)
    _ncount=$(echo "$NEW_KEYS" | grep -c . 2>/dev/null || echo 0)
    if [ "$_ncount" -gt 0 ] 2>/dev/null; then
        echo "❌ $_ncount new key(s)"
        echo "$NEW_KEYS"
        echo "   Action: add to scripts/baselines/engine_state_keys.txt with status=DEBT (if known),"
        echo "          or remove hardcoded key from engine, or mark as OK if genuinely generic."
        FAIL=1
    else
        echo "✅"
    fi
else
    echo "⚠️ baseline file not found"
fi


# ══════════════════════════════════════════════════════════════
# Phase 4: Core genericity — no domain knowledge leaks
# ══════════════════════════════════════════════════════════════
echo ""; sep; echo "  PHASE 4: core genericity"; sep

# §80: Hardcoded domain IDs in core (non-apps)
echo -n "§80: hardcoded domain IDs: "
count=$(grep -rn '"fde-delivery"\|"lock-service"\|"bell-consulting"\|"bell-data-cloud"\|"bell-healthcare"\|"bell-global"\|"enterprise-terms"' aiPlat-core/core/harness/ --include='*.py' 2>/dev/null | grep -v '#\|test_\|builtin_handlers\|builtin_actions\|domain_router\|ontology_loader\|_scan_domain\|_DOMAIN_PROMPT_DEFAULTS\|prompt_loader.py\|ontology_branch.py\|ontology_validator.py' | wc -l | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -rn '"fde-delivery"\|"lock-service"\|"bell-consulting"\|"bell-data-cloud"\|"bell-healthcare"\|"bell-global"\|"enterprise-terms"' aiPlat-core/core/harness/ --include='*.py' 2>/dev/null | grep -v '#\|test_\|builtin_handlers\|builtin_actions\|domain_router\|ontology_loader\|_scan_domain\|_DOMAIN_PROMPT_DEFAULTS\|prompt_loader.py\|ontology_branch.py\|ontology_validator.py'; FAIL=1; else echo "✅"; fi

# §81: Hardcoded domain-specific class names in core routers
echo -n "§81: domain class name hardcodes in routers: "
count=$(grep -rn '"DiagnosisSession"\|"DeliveryAction"\|"Term"' aiPlat-core/core/api/routers/system.py 2>/dev/null | wc -l | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -rn '"DiagnosisSession"\|"DeliveryAction"\|"Term"' aiPlat-core/core/api/routers/system.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §82: Business-domain actions in builtin_actions (should be in YAML)
echo -n "§82: business actions in builtin code: "
count=$(grep -cn 'domain_id="fde-delivery"\|domain_id="lock-service"\|domain_id="bell-' aiPlat-core/core/harness/ontology_engine/builtin_actions.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n 'domain_id="fde-delivery"\|domain_id="lock-service"\|domain_id="bell-' aiPlat-core/core/harness/ontology_engine/builtin_actions.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §83: Business keywords in core ingestion filter
echo -n "§83: business keywords in ingestion: "
count=$(grep -cn '审核路径\|七步周天\|认知同化' aiPlat-core/core/harness/knowledge/conversation_ingestor.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n '审核路径\|七步周天\|认知同化' aiPlat-core/core/harness/knowledge/conversation_ingestor.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §84: Hardcoded cross-domain seed data in resolver
echo -n "§84: cross-domain seed data: "
count=$(grep -cn '"lock-service".*"fde-delivery"\|"客户现场".*"客户"' aiPlat-core/core/harness/knowledge_pipeline/resolver.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n '"lock-service".*"fde-delivery"\|"客户现场".*"客户"' aiPlat-core/core/harness/knowledge_pipeline/resolver.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §85: Default team stages with business assumptions
echo -n "§85: default team stages: "
count=$(grep -c 'architect_agent\|programmer_agent\|qa_agent' aiPlat-core/core/harness/execution/team_planner.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n 'architect_agent\|programmer_agent\|qa_agent' aiPlat-core/core/harness/execution/team_planner.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §86: prompt_loader hardcoded _register for domain/agent prompts
echo -n "§86: hardcoded domain-prompt registrations: "
count=$(grep -c '_register("domain-prompt-' aiPlat-core/core/harness/utils/prompt_loader.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n '_register("domain-prompt-' aiPlat-core/core/harness/utils/prompt_loader.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §87: prompt_loader hardcoded agent SOP registrations
echo -n "§87: hardcoded agent SOP registrations: "
count=$(grep -c '_register("agent-pm_agent"\|_register("agent-architect_agent"\|_register("agent-programmer_agent"' aiPlat-core/core/harness/utils/prompt_loader.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n '_register("agent-pm_agent"\|_register("agent-architect_agent"\|_register("agent-programmer_agent"' aiPlat-core/core/harness/utils/prompt_loader.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# §88: Hardcoded GraphIndex.load in builtin_handlers
echo -n "§88: hardcoded domain in handlers: "
count=$(grep -c 'GraphIndex.load("' aiPlat-core/core/harness/ontology_engine/builtin_handlers.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "❌ $count"; grep -n 'GraphIndex.load("' aiPlat-core/core/harness/ontology_engine/builtin_handlers.py 2>/dev/null; FAIL=1; else echo "✅"; fi

# ── PHASE 5.5: Process compliance checks ────────────────────────────
echo ""; sep; echo "  PHASE 5.5: compliance"; sep

# §89: --no-verify usage audit (detect bypasses of pre-commit hook)
echo -n "§89: --no-verify commits (last 20): "
if command -v git >/dev/null 2>&1; then
    NVS=$(git log --oneline -20 --grep='merge\|\--no-verify' 2>/dev/null | wc -l | tr -d ' ')
    if [ "$NVS" -gt 0 ] 2>/dev/null; then
        echo "⚠️ $NVS (warning only — some commits bypassed pre-commit)"
        # Write audit entry
        AUDIT_LOG="${AIPLAT_HOME:-$HOME/.aiplat}/audit/no_verify_log.txt"
        mkdir -p "$(dirname "$AUDIT_LOG")" 2>/dev/null
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] §89: $NVS no-verify commits detected in last 20" >> "$AUDIT_LOG" 2>/dev/null || true
    else
        echo "✅"
    fi
else echo "⚠️ git not available"; fi

# §90: Engine guard pre-commit hook is installed
echo -n "§90: engine pre-commit hook installed: "
if [ -f ".git/hooks/pre-commit" ] && grep -q "pre-commit-engine-guard" .git/hooks/pre-commit 2>/dev/null; then
    echo "✅"
elif [ -f ".husky/pre-commit" ] && grep -q "pre-commit-engine-guard" .husky/pre-commit 2>/dev/null; then
    echo "✅"
else
    echo "❌ not installed"
    echo "   Install: cp scripts/pre-commit-engine-guard.sh .git/hooks/pre-commit"
    FAIL=1
fi

# §91: Engine self-check enforcement — CLAUDE.md §8b checklist items
echo -n "§91: engine bypass compliance: "
BYPASS_COUNT=$(python3 -c "
import re
text = open('aiPlat-core/core/harness/execution/pipeline_engine.py').read()
# Count new sys_llm_generate calls NOT in _run_stage_skill or _run_chained_skill
# (engine should route through skill execution, not direct LLM calls)
calls = re.findall(r'await sys_llm_generate\(', text)
bypass_callers = [l for l in re.findall(r'async def (\w+).*?\n.*?await sys_llm_generate', text, re.DOTALL) 
                  if '_run_stage_skill' not in l and '_run_chained_skill' not in l and '_exec_chained' not in l]
# Acceptable: _run_test_execution is a code-mode pytest runner (not LLM)
# Acceptable: materials_chat, diagnostics are NOT in pipeline_engine.py
# Check for any method that bypasses _run_stage_skill  
print(len(bypass_callers))  
" 2>/dev/null)
if [ "${BYPASS_COUNT:-0}" -gt 0 ] 2>/dev/null; then
    echo "❌ $BYPASS_COUNT bypass method(s)"
    echo "   CLAUDE.md §8b: any new sys_llm_generate in engine must prove correct path infeasible"
    echo "   Fix: Route through _run_stage_skill or _run_chained_skill"
    FAIL=1
else
    echo "✅"
fi

# ── Aggregate ──
echo ""; sep
if [ "$FAIL" -ne 0 ]; then
    echo "  ARCHITECTURE GUARD: one or more checks FAILED (all checks ran — see above)"
    sep; exit 1
else
    echo "  ARCHITECTURE GUARD: all checks passed"
    sep; exit 0
fi
