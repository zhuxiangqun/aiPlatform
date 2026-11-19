"""N09 K63 — domain_id runtime via DomainRouter.default_graph_domain()."""
from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


from core.harness.knowledge.domain_router import DomainRouter

TARGETS = [
    "aiPlat-core/core/harness/knowledge/domain_router.py",
    "aiPlat-core/core/harness/knowledge_pipeline/extractor.py",
    "aiPlat-core/core/apps/fde/service/extraction_confirm.py",
    "aiPlat-core/core/apps/fde/service/ontology_code_suggestions.py",
    "aiPlat-core/core/apps/fde/service/k_wave_signal.py",
    "aiPlat-core/core/apps/fde/service/offline_owl_review.py",
    "aiPlat-core/core/apps/fde/service/k_wave_case.py",
    "aiPlat-core/core/harness/knowledge/ontology_case_learning.py",
    "aiPlat-core/core/harness/knowledge/conversation_ingestor.py",
    "aiPlat-core/core/harness/actions/action_bridge.py",
    "aiPlat-core/core/harness/ontology_engine/business_event_bridge.py",
    "aiPlat-core/core/harness/ontology_engine/action_registry.py",
    "aiPlat-core/core/api/routers/agents.py",
    "aiPlat-core/core/api/routers/diagnostics.py",
    "aiPlat-core/core/apps/agents/materials_chat.py",
    "aiPlat-core/core/api/routers/wiki_ontology_engine.py",
    "aiPlat-core/core/harness/optimization/abstract_goal_decomposer.py",
    "aiPlat-core/core/harness/learning/experience_vector.py",
    "aiPlat-core/core/harness/coordination/patterns/graph_consensus.py",
    "aiPlat-core/core/engine/skills/domain_assessor/handler.py",
    "aiPlat-core/core/harness/syscalls/retrieval_crag.py",
    "aiPlat-platform/apps/fde/api/extraction_routes.py",
    "aiPlat-platform/apps/fde/api/fde.py",
    "aiPlat-platform/apps/fde/api/action_routes.py",
]


def test_helper_stable():
    assert DomainRouter.default_graph_domain() == "default"
    assert DomainRouter().default_graph_domain() == "default"
    # default_kb_domain 仍为实例方法（ai-knowledge），与 graph catch-all 不同
    assert DomainRouter.default_graph_domain() != DomainRouter().default_kb_domain()


def test_targets_use_domain_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "default_graph_domain()" in text or "PLATFORM_DEFAULT_GRAPH_DOMAIN" in text, rel
        assert 'domain_id or "default"' not in text, rel
        assert 'get("domain_id", "default")' not in text, rel


def test_target_runtime_domain_fallbacks_empty():
    """K63 targets: no remaining domain_id \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_graph_domain" in ln or "PLATFORM_DEFAULT_GRAPH" in ln or "default_tenant" in ln:
                continue
            if "default_collection" in ln or "default_session" in ln or "PLATFORM_DEFAULT" in ln:
                continue
            low = ln.lower()
            if "domain" not in low:
                continue
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']domain_id["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
