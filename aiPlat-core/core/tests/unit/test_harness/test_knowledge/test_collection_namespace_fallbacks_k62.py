"""N09 K62 — collection_id / memory namespace runtime via DomainRouter helpers."""
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
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/api/facades/kb_facade.py",
    "aiPlat-core/core/api/routers/knowledge.py",
    "aiPlat-core/core/apps/tools/kb_tools.py",
    "aiPlat-core/core/harness/knowledge/wiki_read_model.py",
    "aiPlat-core/core/harness/memory/session_wiki.py",
    "aiPlat-core/core/services/conversations.py",
    "aiPlat-core/core/engine/skills/knowledge_retrieval/handler.py",
    "aiPlat-core/core/harness/infrastructure/gates/policy_gate.py",
    "aiPlat-core/core/api/routers/diagnostics.py",
    "aiPlat-platform/api/rest/routes.py",
    "aiPlat-platform/kb/query_telemetry.py",
    "aiPlat-platform/delivery/kb_health.py",
    "aiPlat-platform/delivery/monthly_ops_report.py",
    "aiPlat-core/core/harness/memory/manager.py",
    "aiPlat-core/core/harness/syscalls/retrieval.py",
]


def test_helper_stable():
    assert DomainRouter.default_collection() == "default"
    assert DomainRouter.default_session() == "default"


def test_targets_use_collection_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert (
            "DomainRouter.default_collection()" in text
            or "DomainRouter.default_session()" in text
        ), rel
        assert 'collection_id or "default"' not in text, rel
        assert 'get("collection_id", "default")' not in text, rel


def test_target_runtime_collection_namespace_fallbacks_empty():
    """K62 targets: no remaining collection/namespace \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_collection" in ln or "default_session" in ln or "PLATFORM_DEFAULT" in ln:
                continue
            low = ln.lower()
            if "collection" not in low and "namespace" not in low:
                continue
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']collection_id["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'namespace="default"' in ln or "namespace='default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
