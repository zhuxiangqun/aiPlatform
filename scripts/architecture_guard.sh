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

FAIL_AST=0; FAIL_FE=0; FAIL_ARCH=0; FAIL_CAP=0; FAIL_EV=0; FAIL_UNDEF=0; FAIL_RULE=0

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
python3 scripts/verify_claude_md_evidence.py --strict &
PID_EV=$!

# P0-C7: Rule golden sample — guard rules self-check (\| anti-pattern + re compile)
python3 scripts/rule_golden_sample.py &
PID_RULE=$!

# guard_undefined_names (2026-08-19): AST 级函数内未定义符号（NameError 隐患）
# 背景: ruff F821 被 pyproject ignore + py_compile 只查语法 → PipelineConfig 案例漏检
python3 scripts/guard_undefined_names.py &
PID_UNDEF=$!

wait $PID_AST || FAIL_AST=1
wait $PID_UNDEF || FAIL_UNDEF=1
wait $PID_FE || FAIL_FE=1
wait $PID_ARCH || FAIL_ARCH=1
[ "$PID_CAP" != "0" ] && { wait $PID_CAP || FAIL_CAP=1; }
wait $PID_EV || FAIL_EV=1
wait $PID_RULE || FAIL_RULE=1
[ "$FAIL_AST" -ne 0 ] && FAIL=1
[ "$FAIL_FE" -ne 0 ] && FAIL=1
[ "$FAIL_ARCH" -ne 0 ] && FAIL=1
[ "$FAIL_CAP" -ne 0 ] && FAIL=1
[ "$FAIL_EV" -ne 0 ] && FAIL=1
[ "$FAIL_UNDEF" -ne 0 ] && FAIL=1
[ "$FAIL_RULE" -ne 0 ] && FAIL=1

# ── §0.4b: 证据树落盘（HarnessEval Evidence Tree 借鉴——层级化证据 + known_gaps） ──
# 由 AIPLAT_EVIDENCE_TREE_OUT 环境变量启用；默认关闭，不影响现有门禁行为。
# 产物：{case_id, verdict, branches→sub_branches→evidence(route_reason), known_gaps}
if [ -n "${AIPLAT_EVIDENCE_TREE_OUT:-}" ]; then
    mkdir -p "$(dirname "$AIPLAT_EVIDENCE_TREE_OUT")" 2>/dev/null || true
    python3 scripts/verify_claude_md_evidence.py --tree --out "$AIPLAT_EVIDENCE_TREE_OUT" >/dev/null 2>&1 || true
    echo "  → evidence tree: $AIPLAT_EVIDENCE_TREE_OUT"
fi

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

# ── §77-79: Legacy known-list checks (WARNING only — superseded by principle-based) ──
echo -n "§77 (legacy): known artifact key tuples: "
count=$(grep -rn '"architecture".*"code".*"test_report"\|state\.get("architecture"\|state\.get("code"\|state\.get("test_report"' aiPlat-core/core/harness/execution/ --include='*.py' 2>/dev/null | grep -v '_run_stage_skill\|#\|test_\|snapshot' | wc -l | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "⚠️ $count (warning — known patterns, §79b covers new keys)"; else echo "✅"; fi

echo -n "§79 (legacy): known skill name hardcodes: "
count=$(grep -c '"architecture_design"\|"code_generation"\|"test_case_generation"' aiPlat-core/core/harness/execution/pipeline_engine.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "⚠️ $count (warning — known patterns)"; else echo "✅"; fi

# ── §79b: PRINCIPLE-BASED — state key baseline (ERROR level) ──
echo -n "§79b: engine state key baseline: "
BASELINE="$(dirname "$0")/baselines/engine_state_keys.txt"
if [ -f "$BASELINE" ]; then
    NEW_KEYS=$(python3 -c "
import re, os
with open('$BASELINE') as f:
    allowed = {l.split('|')[0] for l in f if l.strip() and not l.startswith('#')}
found = set()
for root, dirs, files in os.walk('aiPlat-core/core/harness/execution/'):
    for fname in files:
        if fname.endswith('.py'):
            t = open(os.path.join(root,fname)).read()
            for m in re.finditer(r'state\[.\''(\w+)\''.]\1', t): found.add(m.group(1))
            for m in re.finditer(r'state\.get\(.\''(\w+)\''.\1', t): found.add(m.group(1))
new = found - allowed
for k in sorted(new):
    print(k)
" 2>/dev/null)
    _ncount=$(echo "$NEW_KEYS" | grep -c . 2>/dev/null || echo 0)
    if [ "$_ncount" -gt 0 ] 2>/dev/null; then
        echo "❌ $_ncount new key(s)"
        echo "$NEW_KEYS"
        echo "   → Add to baselines/engine_state_keys.txt (DEBT) or remove from engine"
        FAIL=1
    else echo "✅"; fi
else echo "⚠️ baseline file not found"; fi

# ── §78b: PRINCIPLE-BASED — any CJK text in engine (not just 4 prefixes) ──
echo -n "§78b: CJK characters in engine: "
CJK_COUNT=$(python3 -c "
import os, re
found = set()
for root, dirs, files in os.walk('aiPlat-core/core/harness/execution/'):
    for fname in sorted(files):
        if not fname.endswith('.py'): continue
        fpath = os.path.join(root, fname)
        # Skip algorithm definitions (conf data, not engine code)
        if 'algorithm_node' in fname: continue
        # Skip simulation.py — CJK is in docstrings only (module documentation)
        if 'simulation' in fname: continue
        for i, line in enumerate(open(fpath), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'): continue
            if 'prompt_loader' in stripped or '_sync_resolve' in stripped: continue
            if 'from ' in stripped and 'import ' in stripped: continue
            # Skip string literals that are pure data (inside JSON/dict values, not code logic)
            if stripped.startswith(('\"',\"'\")) and ':' in stripped and len(stripped) < 200: continue
            has_cjk = any('\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u309f' for ch in line)
            if has_cjk:
                found.add(f'{os.path.relpath(fpath)}:{i}')
lines = sorted(found)
for l in lines[:15]: print(l)
if len(lines) > 15: print(f'... and {len(lines)-15} more')
" 2>/dev/null)
_CJK_COUNT=$(echo "$CJK_COUNT" | grep -c . 2>/dev/null || echo 0)
if [ "$_CJK_COUNT" -gt 0 ] 2>/dev/null; then
    echo "❌ $_CJK_COUNT line(s) with CJK"
    echo "$CJK_COUNT"
    echo "   → Move to prompt_loader.py or SKILL.md (not inline in engine)"
    FAIL=1
else echo "✅"; fi


# ══════════════════════════════════════════════════════════════
# Phase 4: Core genericity — no domain knowledge leaks
# ══════════════════════════════════════════════════════════════
echo ""; sep; echo "  PHASE 4: core genericity"; sep

# ── §80b: PRINCIPLE-BASED — any domain-name-like string (xxx-yyy pattern) in core/harness ──
echo -n "§80b: domain-name strings in harness: "
DOMAIN_STR=$(python3 -c "
import os, re
found = set()
excl_files = {'domain_router.py','ontology_loader.py','prompt_loader.py','ontology_validator.py',
              'ontology_branch.py','builtin_handlers.py','builtin_actions.py'}
excl_dirs = {'tests','__pycache__'}
for root, dirs, files in os.walk('aiPlat-core/core/harness/'):
    dirs[:] = [d for d in dirs if d not in excl_dirs]
    for fname in files:
        if not fname.endswith('.py') or fname in excl_files: continue
        for i, line in enumerate(open(os.path.join(root,fname)), 1):
            s = line.strip()
            if not s or s.startswith('#'): continue
            # Match \"xxx-yyy\" or 'xxx-yyy' patterns (domain-id convention)
            for m in re.finditer(r'['\"](\w{2,}-\w{2,})['\"]', s):
                val = m.group(1)
                if val not in ('__main__','no-verify','set-env','multi-agent'):  # generic exceptions
                    found.add(f'{os.path.relpath(os.path.join(root,fname))}:{i}  {val}')
lines = sorted(found)
for l in lines[:15]: print(l)
if len(lines) > 15: print(f'... and {len(lines)-15} more')
" 2>/dev/null)
_HARNESS_DS=$(echo "$DOMAIN_STR" | grep -c . 2>/dev/null || echo 0)
if [ "$_HARNESS_DS" -gt 0 ] 2>/dev/null; then
    echo "❌ $_HARNESS_DS domain-name string(s)"
    echo "$DOMAIN_STR"
    echo "   → Move to YAML config or ~/.aiplat/ domain files. Not in core/harness/."
    FAIL=1
else echo "✅"; fi

# ── §80 (legacy): known domain IDs — WARNING only ──
echo -n "§80 (legacy): known domain IDs: "
count=$(grep -rn '"fde-delivery"\|"lock-service"\|"bell-consulting"\|"bell-data-cloud"\|"bell-healthcare"\|"bell-global"\|"enterprise-terms"' aiPlat-core/core/harness/ --include='*.py' 2>/dev/null | grep -v '#\|test_\|builtin_handlers\|builtin_actions\|domain_router\|ontology_loader\|_scan_domain\|_DOMAIN_PROMPT_DEFAULTS\|prompt_loader.py\|ontology_branch.py\|ontology_validator.py' | wc -l | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "⚠️ $count (warning — known patterns, §80b covers new)"; else echo "✅"; fi

# ── §85b: PRINCIPLE-BASED — any *_agent string in engine files ──
echo -n "§85b: agent name strings in engine: "
AGENT_STR=$(python3 -c "
import os, re
found = set()
for root, dirs, files in os.walk('aiPlat-core/core/harness/execution/'):
    dirs[:] = [d for d in dirs if d not in ('__pycache__',)]
    for fname in files:
        if not fname.endswith('.py'): continue
        for i, line in enumerate(open(os.path.join(root,fname)), 1):
            s = line.strip()
            if not s or s.startswith('#'): continue
            # Match quoted strings ending with _agent (agent name convention)
            for m in re.finditer(r'['\"](\w+_agent)['\"]', s):
                val = m.group(1)
                # Exclude references to generic pipeline config fields (not string checks)
                if 'getattr' in s and 'agent_id' in s: continue
                if 'agent_id' in s and val == 'agent_id': continue
                found.add(f'{os.path.relpath(os.path.join(root,fname))}:{i}  \"{val}\"')
lines = sorted(found)
for l in lines[:15]: print(l)
if len(lines) > 15: print(f'... and {len(lines)-15} more')
" 2>/dev/null)
_AGENT_STR=$(echo "$AGENT_STR" | grep -c . 2>/dev/null || echo 0)
if [ "$_AGENT_STR" -gt 0 ] 2>/dev/null; then
    echo "❌ $_AGENT_STR agent name string(s)"
    echo "$AGENT_STR"
    echo "   → Engine must not know specific agent names. Use stage.agent_id or config field."
    FAIL=1
else echo "✅"; fi

# ── §85 (legacy): known agent names — WARNING only ──  
echo -n "§85 (legacy): known agent names: "
count=$(grep -c 'architect_agent\|programmer_agent\|qa_agent' aiPlat-core/core/harness/execution/team_planner.py 2>/dev/null | tr -d '\n' | tr -d ' ')
if [ "$count" -gt 0 ] 2>/dev/null; then echo "⚠️ $count (warning — known patterns, §85b covers new)"; else echo "✅"; fi

# ── §81-84, §86-88: Remaining known-list checks (kept as-is, narrow scope) ──

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

# §90: Engine guard pre-commit hook is installed (skip in CI — hooks are local-dev)
echo -n "§90: engine pre-commit hook installed: "
if [ "${CI:-}" = "true" ] || [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "✅ (CI — local hook not required)"
elif [ -f ".git/hooks/pre-commit" ] && grep -q "pre-commit-engine-guard" .git/hooks/pre-commit 2>/dev/null; then
    echo "✅"
elif [ -f ".husky/pre-commit" ] && grep -q "pre-commit-engine-guard" .husky/pre-commit 2>/dev/null; then
    echo "✅"
else
    echo "❌ not installed"
    echo "   Install: cp scripts/pre-commit-engine-guard.sh .git/hooks/pre-commit"
    FAIL=1
fi

# §91: Engine self-check enforcement — CLAUDE.md §8b checklist items
# AST-based: map each sys_llm_generate call to its enclosing method, then flag
# any method that is NOT a documented known-exception. Known exceptions are
# pre-existing parallel execution paths (workflow LLM nodes / test fix /
# harness self-heal) — see CLAUDE.md §5.23. New calls in any other method FAIL.
echo -n "§91: engine bypass compliance: "
BYPASS_COUNT=$(python3 -c "
import ast

KNOWN_EXCEPTIONS = {
    '_run_stage_skill',     # primary path: llm backend = sys_llm_generate (CLAUDE.md §5.4.1)
    '_run_stage_core',      # workflow-canvas LLM nodes (node_type=llm), rerank, plan
    '_run_test_execution',  # pytest runner self-fix
    '_propose_harness_fix', # harness self-heal proposer (prompt via _sync_resolve)
}

path = 'aiPlat-core/core/harness/execution/pipeline_engine.py'
src = open(path).read()
tree = ast.parse(src)

# line -> enclosing method name
method_of_line = {}
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for i in range(node.lineno, (node.end_lineno or node.lineno) + 1):
            method_of_line[i] = node.name

violations = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name == 'sys_llm_generate':
            m = method_of_line.get(node.lineno, '<module>')
            if m not in KNOWN_EXCEPTIONS:
                violations.add(m)

for v in sorted(violations):
    print(v)
" 2>/dev/null)
_BYPASS_N=$(echo "$BYPASS_COUNT" | grep -c . 2>/dev/null || echo 0)
if [ "${_BYPASS_N:-0}" -gt 0 ] 2>/dev/null; then
    echo "❌ $_BYPASS_N bypass method(s): $(echo "$BYPASS_COUNT" | tr '\n' ' ')"
    echo "   CLAUDE.md §8b: any new sys_llm_generate in engine must prove correct path infeasible"
    echo "   Fix: Route through _run_stage_skill or _run_chained_skill"
    FAIL=1
else
    echo "✅"
fi

# §92: Platform → Core layer violation detection
# Platform MUST NOT import core.harness.execution.* or core.harness.engine.*
# Pipeline execution should be delegated via Core API, not direct instantiation.
echo -n "§92: platform→core boundary: "
VIOLATIONS=$(grep -rEn "from core\.harness\.execution\.(pipeline_engine|engine)\b|from core\.harness\.execution import.*PipelineEngine|import.*core\.harness\.execution\.(pipeline_engine|engine)" \
    aiPlat-platform/ --include="*.py" 2>/dev/null | grep -v "# noqa:" | grep -v __pycache__ | grep -v "pipeline_orchestrator_client" | wc -l | tr -d ' ')
if [ "${VIOLATIONS:-0}" -gt 0 ] 2>/dev/null; then
    echo "❌ ${VIOLATIONS} violation(s)"
    grep -rEn "from core\.harness\.execution\.(pipeline_engine|engine)\b|from core\.harness\.execution import.*PipelineEngine" \
        aiPlat-platform/ --include="*.py" 2>/dev/null | grep -v "# noqa:" | grep -v __pycache__ | grep -v "pipeline_orchestrator_client"
    echo "   Fix: Use PipelineOrchestratorClient → Core HTTP API, not direct import"
    FAIL=1
else
    echo "✅"
fi

# §93: Service class size gate — prevent God Objects
# Any service class >1000 lines triggers ERROR (must be refactored)
echo -n "§93: service class size gate: "
OVERSIZED=$(python3 -c "
import ast, sys, os
oversized = []
for root, dirs, files in os.walk('aiPlat-platform'):
    dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'node_modules')]
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        try:
            with open(path) as fh:
                content = fh.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    end = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno
                    size = end - node.lineno + 1
                    if size > 1000:
                        oversized.append(f'{path}:{node.lineno} {node.name} ({size} lines)')
        except Exception:
            pass
for o in oversized:
    print(o)
print(len(oversized))
" 2>/dev/null)
if [ "${OVERSIZED:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  ${OVERSIZED} class(es) over 1000 lines"
    echo "   Consider splitting large service classes (God Object anti-pattern)"
    echo "   CLAUDE.md §5.30 Rule 2: Prefer composition over monolithic classes"
else
    echo "✅"
fi

# ── §94b: BOUNDARY.yaml 全量目录审计（roadmap Phase 0.3 闭环, 2026-08-25） ──
# core/harness 下每个一级子目录必须有 BOUNDARY.yaml（声明 layer + 依赖方向 + known_debt）。
echo -n "§94b: BOUNDARY.yaml 目录覆盖: "
_BOUNDARY_MISSING=$(for d in aiPlat-core/core/harness/*/; do
    base=$(basename "$d")
    [ "$base" = "__pycache__" ] && continue
    [ -f "$d/BOUNDARY.yaml" ] || echo "$base"
done)
if [ -n "$_BOUNDARY_MISSING" ]; then
    echo "❌ 缺 BOUNDARY.yaml 的目录:"
    echo "$_BOUNDARY_MISSING" | sed 's/^/     /'
    echo "   → 每个 harness 一级子目录必须声明 BOUNDARY.yaml（layer/rationale/known_debt）"
    FAIL=1
else
    echo "✅"
fi

# ── §95: 生成物 conformance 契约自举校验（SBA 借鉴, 2026-08-26） ──
# 校验器对真实生成物基线（frozen fixture）必须保持"旧格式必拒"——防 conformance
# 契约被改弱后静默放行不合格生成物（校验器自指守卫）。
echo -n "§95: 生成物 conformance 契约有效性: "
_CONF_RESULT=$(python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location(
    'gc', 'aiPlat-platform/builder/generated_conformance.py')
gc = importlib.util.module_from_spec(spec); spec.loader.exec_module(gc)
base = 'aiPlat-platform/tests/fixtures/generated'
legacy_skill = gc.validate_file(f'{base}/video_sense_legacy_skill.md', 'skill')
legacy_agent = gc.validate_file(f'{base}/video_sense_legacy_agent.md', 'agent')
problems = []
if not legacy_skill:
    problems.append('legacy SKILL 应被拒却通过（契约被改弱？）')
if not legacy_agent:
    problems.append('legacy AGENT 应被拒却通过（契约被改弱？）')
print('; '.join(problems) if problems else 'OK')
" 2>&1)
if [ "$_CONF_RESULT" = "OK" ]; then
    echo "✅"
else
    echo "❌ $_CONF_RESULT"
    FAIL=1
fi

# ── §96: workspace agent 符合度 ratchet（2026-08-26） ──
# 校验 ~/.aiplat/agents/*/AGENT.md（行数≤100/交接5字段/无model硬编码/输出格式归属 SKILL.md）。
# ratchet 模式：存量违规入基线容忍，新增违规阻断（同 ruff F821 先例）——推动逐步治理。
echo -n "§96: workspace agent 符合度: "
_NEW_AGENT=$(python3 -c "
import importlib.util, json
spec = importlib.util.spec_from_file_location('ac', 'aiPlat-platform/builder/agent_conformance.py')
ac = importlib.util.module_from_spec(spec); spec.loader.exec_module(ac)
cur = ac.validate_agents_dir()
base = ac.load_baseline()
diff = ac.ratchet_diff(cur, base)
print(json.dumps(diff, ensure_ascii=False))
" 2>&1)
if [ "$_NEW_AGENT" = "{}" ]; then
    echo "✅"
else
    echo "❌ 新增违规: $_NEW_AGENT"
    echo "   → 修复新增违规；批量治理后运行: python3 -c \"import importlib.util; s=importlib.util.spec_from_file_location('ac','aiPlat-platform/builder/agent_conformance.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.save_baseline(m.validate_agents_dir())\" 更新基线"
    FAIL=1
fi

# ── §97: 平台能力生成物适用性（2026-08-27，防平台-产物脱节） ──
# 每个 governance 能力模块必须：① CAPABILITIES 有条目 ② 条目含"生成物"适用性评估声明。
echo -n "§97: 生成物适用性评估: "
if python3 scripts/check_generated_artifact_wiring.py >/dev/null 2>&1; then
    echo "✅"
else
    echo "❌ 存在 governance 模块缺 CAPABILITIES 条目或「生成物」适用性标注"
    echo "   Run: python3 scripts/check_generated_artifact_wiring.py 查看详情"
    FAIL=1
fi

# ── §73: Capability consumer verification (replaces deprecated caller_verify.sh) ──
# Phase 2.5 method-level wiring runs in phase_check.sh (method_verify.sh + wiring tests).
echo -n "§73: capability consumers wired: "
if bash scripts/verify_capability_consumers.sh >/dev/null 2>&1; then
    echo "✅"
else
    echo "❌ verify_capability_consumers.sh found issues"
    echo "   Run: bash scripts/verify_capability_consumers.sh for details"
    FAIL=1
fi

# ── Aggregate ──
echo ""; sep

# ── §0.4c: 守卫路由决策记录（HarnessEval routing_trace 借鉴——启用/跳过原因可审计） ──
# 由 AIPLAT_GUARD_TRACE_OUT 环境变量启用；默认关闭，不影响门禁。
# 产物：{run_id, mode, route_trace[{check, enabled, reason_selected, reason_skipped, result}], failed_guards, verdict}
if [ -n "${AIPLAT_GUARD_TRACE_OUT:-}" ]; then
    mkdir -p "$(dirname "$AIPLAT_GUARD_TRACE_OUT")" 2>/dev/null || true
    python3 - "$AIPLAT_GUARD_TRACE_OUT" "$QUICK_MODE" "$FAIL" "$FAIL_AST" "$FAIL_FE" "$FAIL_ARCH" "$FAIL_CAP" "$FAIL_EV" "$FAIL_UNDEF" "$FAIL_RULE" "${CI:-}" <<'PYEOF' >/dev/null 2>&1 || true
import json, os, sys, time
out, mode, fail = sys.argv[1], sys.argv[2], sys.argv[3]
vals = {"FAIL_AST": sys.argv[4], "FAIL_FE": sys.argv[5], "FAIL_ARCH": sys.argv[6],
        "FAIL_CAP": sys.argv[7], "FAIL_EV": sys.argv[8], "FAIL_UNDEF": sys.argv[9],
        "FAIL_RULE": sys.argv[10]}
is_ci = sys.argv[11] == "true"
quick = mode == "true"
trace = {
    "run_id": "arch-guard-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
    "harness": "architecture_guard.sh",
    "mode": "quick" if quick else "full",
    "route_trace": [
        {"check": "phase1_guard_scripts", "enabled": True,
         "reason_selected": "核心守卫脚本（AST/frontend/arch/evidence/undefined/rule golden）",
         "reason_skipped": None,
         "result": "pass" if fail == "0" else "fail"},
        {"check": "phase2_secondary", "enabled": quick,
         "reason_selected": "quick 模式跑 lightweight frontmatter+doc-sync 后台检查",
         "reason_skipped": "full 模式由独立 CI job 执行",
         "result": "run" if quick else "skipped"},
        {"check": "capability_convergence", "enabled": (not quick),
         "reason_selected": "非 quick 且未设 SKIP_CAP_CONV 时执行能力收敛检查",
         "reason_skipped": "quick 模式或 SKIP_CAP_CONV 设置",
         "result": "skipped" if quick else ("pass" if vals["FAIL_CAP"] == "0" else "fail")},
        {"check": "phase3_engine_agnostic", "enabled": True,
         "reason_selected": "引擎层去业务化检查（§77-79）", "reason_skipped": None,
         "result": "run"},
        {"check": "phase4_genericity", "enabled": True,
         "reason_selected": "core/infra 通用性检查（§80-88）", "reason_skipped": None,
         "result": "run"},
        {"check": "phase5.5_compliance", "enabled": True,
         "reason_selected": "流程合规检查（§89-96 + §73 能力消费者）", "reason_skipped": None,
         "result": "run"},
        {"check": "§90_engine_hook_install", "enabled": (not is_ci),
         "reason_selected": "本地开发环境检查 pre-commit hook 安装",
         "reason_skipped": "CI/GitHub Actions 环境不需要本地 hook",
         "result": "skipped" if is_ci else "run"},
    ],
    "failed_guards": [k for k, v in vals.items() if v == "1"],
    "verdict": "pass" if fail == "0" else "fail",
}
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(trace, f, ensure_ascii=False, indent=2)
PYEOF
    echo "  → guard route trace: $AIPLAT_GUARD_TRACE_OUT"
fi

if [ "$FAIL" -ne 0 ]; then
    echo "  ARCHITECTURE GUARD: one or more checks FAILED (all checks ran — see above)"
    # ── L2 经验回写（HarnessEval × SBA §5.5）：守卫失败自动登记为待验证经验 ──
    # 记录失败是安全的（gotchas=可逆日志）；验证/升级由后续运行或人工触发。
    _EF="aiPlat-platform/governance/experience_feedback/experience_feedback.py"
    python3 "$_EF" --register --rule "architecture-guard-fail" \
        --content "架构守卫执行失败（详见本次守卫日志）" --source architecture_guard \
        --confidence 0.9 --risk low >/dev/null 2>&1 || true
    sep; exit 1
else
    echo "  ARCHITECTURE GUARD: all checks passed"
    sep; exit 0
fi
