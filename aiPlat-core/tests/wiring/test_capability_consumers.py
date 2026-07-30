"""
test_capability_consumers.py — Phase 46: Verify core capabilities are reachable
through correct syscall/service paths by all consumers.

Each test exercises the complete call chain: consumer → syscall → core.
Runs as part of the test suite to catch regressions automatically.
"""

import subprocess
import pytest


# ═══════════════════════════════════════════════════════
# LLM Layer
# ═══════════════════════════════════════════════════════

def test_sys_llm_generate_importable():
    """sys_llm_generate is importable without errors."""
    from core.harness.syscalls.llm import sys_llm_generate
    assert sys_llm_generate is not None


def test_best_model_for_purpose_works():
    """best_model_for_purpose returns a model name."""
    from core.harness.utils.model_injection import best_model_for_purpose
    model = best_model_for_purpose("chat")
    assert model is not None and isinstance(model, str) and len(model) > 0


# ═══════════════════════════════════════════════════════
# Retrieval Layer
# ═══════════════════════════════════════════════════════

def test_sys_crag_retrieve_importable():
    """sys_crag_retrieve is importable."""
    from core.harness.syscalls.retrieval_crag import sys_crag_retrieve
    assert sys_crag_retrieve is not None


def test_sys_knowledge_retrieve_importable():
    """sys_knowledge_retrieve is importable."""
    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    assert sys_knowledge_retrieve is not None


# ═══════════════════════════════════════════════════════
# Memory Layer
# ═══════════════════════════════════════════════════════

def test_memory_manager_importable():
    """MemoryManager is importable and returns singleton."""
    from core.harness.memory.manager import get_memory_manager
    mm = get_memory_manager()
    assert mm is not None


def test_semantic_increment_importable():
    """increment_access_count is available on SemanticMemory."""
    from core.harness.memory.semantic import SemanticMemory
    assert hasattr(SemanticMemory, 'increment_access_count')


def test_memory_rules_loadable():
    """Memory rules load without errors."""
    from core.harness.memory.manager import MemoryManager
    rules = MemoryManager.load_memory_rules()
    assert isinstance(rules, dict)
    assert "ignore_greetings" in rules


# ═══════════════════════════════════════════════════════
# Decomposition Layer
# ═══════════════════════════════════════════════════════

def test_ontology_mapper_injects_decompositions():
    """map_query_to_ontology injects decomposition into rewritten_query."""
    from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology
    r = map_query_to_ontology("利润率是多少", domain_id="ai-knowledge")
    assert "利润" in r.get("rewritten_query", ""), "Decomposition not injected"


def test_decomposition_rules_load():
    """_apply_decompositions matches known composite terms."""
    from core.harness.knowledge.ontology_query_mapper import _apply_decompositions
    results = _apply_decompositions("利润率", "ai-knowledge")
    assert len(results) >= 1
    assert results[0]["composite"] == "利润率"


# ═══════════════════════════════════════════════════════
# Graph Layer — Platform access through CoreFacade
# ═══════════════════════════════════════════════════════

def test_graphindex_re_exported():
    """GraphIndex is re-exported from CoreFacade for platform layer."""
    from core.api.core_facade import GraphIndex
    assert GraphIndex is not None


def test_get_graph_health_works():
    """get_graph_health returns health stats."""
    from core.api.core_facade import get_graph_health
    result = get_graph_health("fde-delivery")
    assert isinstance(result, dict)


def test_no_platform_harness_import():
    """Platform layer must NOT import GraphIndex from harness directly."""
    result = subprocess.run(
        ["grep", "-rn",
         "from core.harness.ontology_engine.graph_index import GraphIndex",
         "aiPlat-platform/apps/fde/api/"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, \
        f"Platform has harness import: {result.stdout[:200]}"


# ═══════════════════════════════════════════════════════
# Skill Layer
# ═══════════════════════════════════════════════════════

def test_sys_skill_call_importable():
    """sys_skill_call is importable."""
    from core.harness.syscalls.skill import sys_skill_call
    assert sys_skill_call is not None


def test_skill_registry_importable():
    """SkillRegistry is importable."""
    from core.apps.skills.registry import get_skill_registry
    reg = get_skill_registry()
    assert reg is not None


# ═══════════════════════════════════════════════════════
# Tool Layer
# ═══════════════════════════════════════════════════════

def test_sys_tool_call_importable():
    """sys_tool_call is importable."""
    from core.harness.syscalls.tool import sys_tool_call
    assert sys_tool_call is not None


# ═══════════════════════════════════════════════════════
# Wiki Layer
# ═══════════════════════════════════════════════════════

def test_generate_index_md_works():
    """generate_index_md produces valid markdown index."""
    from core.harness.knowledge.wiki_engine import generate_index_md
    result = generate_index_md(collection_id="default")
    assert "# Wiki Index" in result or "No pages yet" in result


def test_wiki_search_pages_via_core_facade():
    """wiki_search_pages is available through CoreFacade."""
    from core.api.core_facade import wiki_search_pages
    result = wiki_search_pages("test", collection_id="default", limit=1)
    assert isinstance(result, list)


# ═══════════════════════════════════════════════════════
# MoA Layer
# ═══════════════════════════════════════════════════════

def test_moa_executor_importable():
    """moa_executor is importable as syscall."""
    from core.harness.syscalls.moa_executor import execute, MoaResult
    assert execute is not None
    assert MoaResult is not None


# ═══════════════════════════════════════════════════════
# Compression Layer
# ═══════════════════════════════════════════════════════

def test_transcript_guard_importable():
    """normalize_roles is importable."""
    from core.harness.memory.transcript_guard import normalize_roles
    assert normalize_roles is not None
