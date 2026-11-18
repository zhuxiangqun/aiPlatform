"""N09 K50 — outer-layer tenant_id signature defaults via DomainRouter.default_tenant()."""
from __future__ import annotations

import re
from pathlib import Path

from core.harness.knowledge.domain_router import DomainRouter

TARGETS = [
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/harness/syscalls/retrieval.py",
    "aiPlat-core/core/harness/memory/file_store.py",
    "aiPlat-core/core/harness/ontology_engine/graph_index.py",
    "aiPlat-core/core/policy/object_permission.py",
    "aiPlat-platform/delivery/kb_health.py",
    "aiPlat-platform/api/rest/routes.py",
]


def test_default_tenant_helper_stable():
    assert DomainRouter.default_tenant() == "default"
    assert DomainRouter.PLATFORM_DEFAULT_TENANT == "default"


def test_targets_use_default_tenant_ssot():
    for rel in TARGETS:
        text = Path(rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_tenant()" in text, rel
        assert 'tenant_id: str = "default"' not in text, rel


def test_production_tenant_signature_defaults_empty():
    rx = re.compile(r'tenant_id\s*:\s*str\s*=\s*["\']default["\']')
    hits = []
    for root in (Path("aiPlat-core/core"), Path("aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p}:{i}")
    assert hits == [], hits
