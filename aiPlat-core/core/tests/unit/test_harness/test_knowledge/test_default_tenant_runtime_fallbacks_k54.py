"""N09 K54 — tenant runtime ``or "default"`` fallbacks via DomainRouter.default_tenant()."""
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
    "aiPlat-core/core/harness/memory/semantic.py",
    "aiPlat-core/core/harness/memory/manager.py",
    "aiPlat-core/core/harness/memory/profile_builder.py",
    "aiPlat-core/core/harness/memory/file_store.py",
    "aiPlat-core/core/harness/memory/migrate_semantic.py",
    "aiPlat-core/core/harness/knowledge_pipeline/retriever.py",
    "aiPlat-core/core/harness/knowledge_pipeline/extractor.py",
    "aiPlat-core/core/harness/ontology_engine/engine.py",
    "aiPlat-core/core/harness/syscalls/retrieval.py",
    "aiPlat-core/core/apps/agents/materials_chat.py",
    "aiPlat-core/core/apps/agents/kb_planner.py",
    "aiPlat-core/core/apps/tools/kb_tools.py",
    "aiPlat-core/core/management/knowledge_manager.py",
    "aiPlat-core/core/apps/diagnosis/service/store.py",
    "aiPlat-core/core/apps/fde/service/k_wave_arbit.py",
    "aiPlat-core/core/apps/eval/service/store.py",
]


def test_helper_stable():
    assert DomainRouter.default_tenant() == "default"


def test_targets_use_default_tenant_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_tenant()" in text, rel
        assert 'tenant_id or "default"' not in text, rel
        assert "(tenant_id or \"\").strip() or \"default\"" not in text, rel


def test_target_runtime_tenant_fallbacks_empty():
    """K54 targets: no remaining tenant_id ... \"default\" runtime fallbacks."""
    rx = re.compile(
        r'(tenant_id\s+or\s+["\']default["\']|'
        r'\(tenant_id or ["\']{2}\)\\.strip\(\) or ["\']default["\']|'
        r'get\(["\']tenant_id["\']\)\s+or\s+["\']default["\'])'
    )
    hits = []
    for rel in TARGETS:
        p = _repo_root() / rel
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "default_tenant" in ln or "PLATFORM_DEFAULT_TENANT" in ln:
                continue
            if rx.search(ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
