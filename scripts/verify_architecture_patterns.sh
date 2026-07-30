#!/usr/bin/env bash
# verify_architecture_patterns.sh
# Phase 45: Detect core capabilities bypassing syscall/service layer.
#
# Rule 1: LLM calls MUST use sys_llm_generate (not create_selected_adapter+.generate)
# Rule 2: ReActLoop MUST go through PipelineEngine
# Rule 3: Retrieval MUST use syscall layer (not direct imports in agents)
#
# Exit 0 = clean, exit 1 = violations

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[verify] Architecture pattern compliance..."

# ── Rule 1: LLM must go through sys_llm_generate ──
echo "  [1/3] LLM calls → sys_llm_generate..."
# Known legitimate: infrastructure modules that create adapters to pass INTO sys_llm_generate
# or training/specialized modules that use isolated agent loops
KNOWN_LLM_EXCEPTIONS="compression.py|manager.py|parsers.py|video.py|dynamic_orchestrator.py|merger.py|voice_loop.py|skill_manager.py|server.py|model_injection.py|retrieval.py|retrieval_crag.py|moa_executor.py|goal_dependency_graph.py|abstract_goal_decomposer.py|tool_bootstrap.py|search_engine.py|auto_trigger.py|wiki_engine.py|sqlite_retriever.py|model_fingerprint.py|pipeline_engine.py|property_extractor.py|relation_mapper.py|rule_designer.py|classifier.py|wiki_ontology_domains.py|workspace_agents.py|mcp_admin.py|knowledge_graph.py|prompt_optimize.py|workspace_skills.py|tools.py|wiki.py|entropy.py|core_facade.py|llm_client.py|base.py|registry.py|executor.py"

LLM_BYPASS=$(grep -rn 'create_selected_adapter' \
    "$ROOT/aiPlat-core/core/" --include='*.py' 2>/dev/null | \
    grep -v 'syscalls/llm.py' | \
    grep -v '/tests/' | \
    grep -v '__pycache__' | \
    grep -vE "$KNOWN_LLM_EXCEPTIONS" || true)

if [ -n "$LLM_BYPASS" ]; then
    echo "    ⚠️  create_selected_adapter in unlisted modules:"
    echo "$LLM_BYPASS" | head -10 | while read -r line; do
        echo "      $line"
    done
    echo "    → These may need review. Add to KNOWN_LLM_EXCEPTIONS if legitimate."
fi

# ── Rule 2: ReActLoop must go through PipelineEngine ──
echo "  [2/3] ReActLoop → PipelineEngine..."
KNOWN_REACT_EXCEPTIONS="pipeline_engine.py|langgraph/stage_runner.py|interfaces/loop.py|_facade.py|profile_builder.py|prompt_optimizer.py|rl_trainer.py"

REACT_BYPASS=$(grep -rn 'ReActLoop(' \
    "$ROOT/aiPlat-core/core/" --include='*.py' 2>/dev/null | \
    grep -vE "$KNOWN_REACT_EXCEPTIONS" | \
    grep -v '/tests/' | \
    grep -v '__pycache__' || true)

if [ -n "$REACT_BYPASS" ]; then
    echo "    ⚠️  ReActLoop instantiated in unlisted modules:"
    echo "$REACT_BYPASS" | while read -r line; do
        echo "      $line"
    done
    echo "    → Should use PipelineEngine for proper lifecycle/memory/compression management."
    echo "    → Or add to KNOWN_REACT_EXCEPTIONS if isolated ReActLoop is intentional."
fi

# ── Rule 3: Retrieval must use syscall layer ──
echo "  [3/3] Retrieval → syscalls..."
KNOWN_RETRIEVAL_EXCEPTIONS="retrieval.py|retrieval_crag.py|retriever.py|sqlite_retriever.py|orchestrated_retrieval.py|knowledge_ontology.py|hyde_expander.py"

RETRIEVAL_BYPASS=$(grep -rn 'ontology_first_retrieve\|hyde_retrieve\|KnowledgeRetriever(' \
    "$ROOT/aiPlat-core/core/" --include='*.py' 2>/dev/null | \
    grep -vE "$KNOWN_RETRIEVAL_EXCEPTIONS" | \
    grep -v '/tests/' | \
    grep -v '__pycache__' || true)

if [ -n "$RETRIEVAL_BYPASS" ]; then
    echo "    ⚠️  Direct retrieval imports in unlisted modules:"
    echo "$RETRIEVAL_BYPASS" | while read -r line; do
        echo "      $line"
    done
    echo "    → Should use sys_crag_retrieve or sys_knowledge_retrieve."
    echo "    → Or add to KNOWN_RETRIEVAL_EXCEPTIONS if definition site."
fi

# ── Rule 4: Memory access must go through MemoryManager ──
echo "  [4/6] Memory access → MemoryManager..."
KNOWN_MEMORY_EXCEPTIONS="semantic.py|ltm_mixin.py|schema.py|migrate_semantic.py|memory_persistence.py"
MEMORY_BYPASS=$(grep -rn 'semantic_memories\|long_term_memories' \
    "$ROOT/aiPlat-core/core/" --include='*.py' 2>/dev/null | \
    grep -vE "$KNOWN_MEMORY_EXCEPTIONS" | \
    grep -v '/tests/' | grep -v '__pycache__' | \
    grep 'UPDATE\|INSERT\|DELETE\|SELECT' | \
    grep -v 'manager.py' || true)

if [ -n "$MEMORY_BYPASS" ]; then
    echo "    ⚠️  Direct SQL on memory tables (should use MemoryManager):"
    echo "$MEMORY_BYPASS" | head -5 | while read -r line; do echo "      $line"; done
    echo "    → Use MemoryManager.increment_semantic_access() or semantic store methods."
fi

# ── Rule 5: GraphIndex must not be imported at platform layer ──
echo "  [5/6] GraphIndex → CoreFacade (platform layer)..."
GRAPH_PLATFORM_BYPASS=$(grep -rn 'from core.harness.*graph_index import\|from core.harness.ontology_engine.graph_index' \
    "$ROOT/aiPlat-platform/" --include='*.py' 2>/dev/null | \
    grep -v '/tests/' | grep -v '__pycache__' || true)

if [ -n "$GRAPH_PLATFORM_BYPASS" ]; then
    echo "    ⚠️  GraphIndex imported at platform layer (should use CoreFacade):"
    echo "$GRAPH_PLATFORM_BYPASS" | head -10 | while read -r line; do echo "      $line"; done
    echo "    → Use CoreFacade.get_graph_health() / get_graph_sessions() / get_graph_neighbors()."
fi

# ── Rule 6: Permission checks must be in PolicyGate ──
echo "  [6/6] Permission checks → PolicyGate..."
KNOWN_PERM_EXCEPTIONS="policy_gate.py|guard.py|rbac.py|server.py|skill_manager.py|agent_manager.py|integration.py|integration/agent.py|integration/skill.py|graph_index.py|workspace_agents.py|mcp_admin.py|traces_graphs.py|workspace_tools.py|workspace_skills.py|evaluation_policies.py|runs.py|core_facade.py|security_facade.py|permission.py|__init__.py|deps/guard.py"
PERM_BYPASS=$(grep -rn 'check_permission\|get_permission_manager' \
    "$ROOT/aiPlat-core/core/" --include='*.py' 2>/dev/null | \
    grep -vE "$KNOWN_PERM_EXCEPTIONS" | \
    grep -v '/tests/' | grep -v '__pycache__' | grep -v 'deps/' || true)

if [ -n "$PERM_BYPASS" ]; then
    echo "    ⚠️  Permission checks outside PolicyGate (may duplicate enforcement):"
    echo "$PERM_BYPASS" | head -10 | while read -r line; do echo "      $line"; done
    echo "    → Per CLAUDE.md §11, only PolicyGate should check permissions."
fi

# ── Rule 7: Deployment must go through DeployEngine/GitPusher ──
echo "  [7/9] Deployment → DeployEngine/GitPusher..."
KNOWN_DEPLOY_EXCEPTIONS="git_pusher.py|deploy_engine.py|pipeline_engine.py|repo.py|skill_marketplace.py|system.py|fde.py"
DEPLOY_BYPASS=$(grep -rn 'git push\|git tag\|docker build\|subprocess.*["'"'"']git["'"'"']\|subprocess.*["'"'"']docker["'"'"']' \
    "$ROOT/aiPlat-core/core/" "$ROOT/aiPlat-platform/" --include='*.py' 2>/dev/null | \
    grep -vE "$KNOWN_DEPLOY_EXCEPTIONS" | \
    grep -v '/tests/' | grep -v '__pycache__' | grep -v 'management/' || true)

if [ -n "$DEPLOY_BYPASS" ]; then
    echo "    ⚠️  Direct git/docker operations outside DeployEngine/GitPusher:"
    echo "$DEPLOY_BYPASS" | head -5 | while read -r line; do echo "      $line"; done
fi

# ── Rule 8: Platform must not import harness modules directly ──
echo "  [8/9] Platform imports → CoreFacade..."
PLATFORM_BYPASS=$(grep -rn 'from core.harness.knowledge.wiki_engine import\|from core.harness.ontology_engine.graph_index import' \
    "$ROOT/aiPlat-platform/" --include='*.py' 2>/dev/null | \
    grep -v '/tests/' | grep -v '__pycache__' || true)

if [ -n "$PLATFORM_BYPASS" ]; then
    echo "    ⚠️  Platform layer importing harness modules (should use CoreFacade):"
    echo "$PLATFORM_BYPASS" | head -5 | while read -r line; do echo "      $line"; done
fi

# ── Rule 9: Context assembly must use MemoryManager ──
echo "  [9/9] Context → MemoryManager..."
KNOWN_CTX_EXCEPTIONS="manager.py|llm.py|compression.py|base.py|coordinator.py|executor.py"
CONTEXT_BYPASS=$(grep -rn 'messages\s*=\s*\[\s*\]' \
    "$ROOT/aiPlat-core/core/" --include='*.py' 2>/dev/null | \
    grep -vE "$KNOWN_CTX_EXCEPTIONS" | \
    grep -v '/tests/' | grep -v '__pycache__' | grep -v 'prompt_loader\|prompt_optimize\|prompt' | \
    grep 'role.*system.*system_prompt\|system.*content.*system_prompt' || true)

if [ -n "$CONTEXT_BYPASS" ]; then
    echo "    ⚠️  Manual message assembly bypassing MemoryManager.build_context:"
    echo "$CONTEXT_BYPASS" | head -5 | while read -r line; do echo "      $line"; done
fi

echo ""
HAS_BYPASS=false
[ -n "${LLM_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${REACT_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${RETRIEVAL_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${MEMORY_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${GRAPH_PLATFORM_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${PERM_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${DEPLOY_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${CONTEXT_BYPASS:-}" ] && HAS_BYPASS=true
[ -n "${PLATFORM_BYPASS:-}" ] && HAS_BYPASS=true

if $HAS_BYPASS; then
    BLOCK="${BLOCK_ARCH_PATTERNS:-1}"  # Phase 46: default BLOCK
    if [ "$BLOCK" != "0" ]; then
        echo ""
        echo "  ❌ Architecture pattern violations detected."
        echo "     Set SKIP_ARCH_PATTERNS=1 to temporarily bypass (NOT recommended)."
        echo "     Or set BLOCK_ARCH_PATTERNS=0 for warnings only."
        exit 1
    fi
    echo "  ⚠️  Warnings only mode (BLOCK_ARCH_PATTERNS=0). Review above."
else
    echo "✅ All architecture patterns clean."
fi
exit 0
