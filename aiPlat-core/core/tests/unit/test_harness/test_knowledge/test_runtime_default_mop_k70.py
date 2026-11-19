"""N09 K70 — mop leftover collection/module/channel/tenant runtime defaults to DomainRouter SSOT."""
from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


from core.harness.knowledge.domain_router import DomainRouter

# 本批清扫目标：K67–K69 漏网的签名/运行时 "default"
TARGETS = [
    "aiPlat-core/core/api/routers/wiki_ontology_export.py",
    "aiPlat-core/core/api/routers/wiki_semantic_suggestions.py",
    "aiPlat-core/core/api/routers/wiki_evidence.py",
    "aiPlat-core/core/api/routers/wiki_writeback.py",
    "aiPlat-core/core/api/routers/wiki_health_quality.py",
    "aiPlat-core/core/api/routers/wiki_ontology_domains.py",
    "aiPlat-core/core/api/routers/wiki_ontology_patterns.py",
    "aiPlat-core/core/api/routers/wiki_field_security.py",
    "aiPlat-core/core/api/routers/wiki_ontology_engine.py",
    "aiPlat-core/core/api/routers/wiki_markings.py",
    "aiPlat-core/core/api/routers/diagnostics.py",
    "aiPlat-core/core/api/routers/wiki.py",
    "aiPlat-core/core/api/routers/diagnostics_capability.py",
    "aiPlat-core/core/harness/learning/success_generalizer.py",
    "aiPlat-core/core/harness/knowledge/wiki_engine.py",
    "aiPlat-core/core/harness/knowledge/staleness_monitor.py",
    "aiPlat-core/core/harness/syscalls/file.py",
    "aiPlat-core/core/harness/execution/pipeline_engine.py",
    "aiPlat-core/core/harness/execution/langgraph/core.py",
    "aiPlat-core/core/apps/agents/materials_chat.py",
    "aiPlat-core/core/services/execution_store/session_mixin.py",
    "aiPlat-core/core/services/execution_store/gateway_mixin.py",
    "aiPlat-platform/api/routers/builder.py",
    "aiPlat-platform/api/routers/conversations.py",
    "aiPlat-platform/api/routers/gateway.py",
    "aiPlat-platform/api/routers/memory_import.py",
    "aiPlat-platform/auth/request_identity.py",
]

SSOT_MARKERS = (
    "default_collection()",
    "default_module_id()",
    "default_label()",
    "default_tenant()",
    "default_session()",
    "default_graph_domain()",
)

FORBIDDEN_NEEDLES = (
    'collection: str = "default"',
    'collection: str = "default",',
    'or "default")',
    "or 'default'",
    'or "default",',
    'module_id") or "default"',
    'channel") or "default"',
    'tid or "default"',
)


def test_helpers_stable():
    assert DomainRouter.default_collection() == "default"
    assert DomainRouter.default_module_id() == "default"
    assert DomainRouter.default_label() == "default"
    assert DomainRouter.default_tenant() == "default"
    assert DomainRouter.default_graph_domain() == "default"


def test_targets_use_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert any(m in text for m in SSOT_MARKERS), rel


def test_target_runtime_default_literals_empty():
    """K70 targets: no leftover collection/module/channel/tenant \"default\" fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(m in ln for m in SSOT_MARKERS):
                continue
            if "purpose=" in ln and '"default"' in ln:
                continue
            for n in FORBIDDEN_NEEDLES:
                if n in ln:
                    hits.append(f"{rel}:{i}:{ln.strip()}")
                    break
    assert hits == [], hits
