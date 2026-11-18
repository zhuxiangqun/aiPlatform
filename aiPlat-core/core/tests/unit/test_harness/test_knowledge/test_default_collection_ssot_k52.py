"""N09 K52 — collection_id / profile_id defaults via DomainRouter SSOT."""
from __future__ import annotations

import re
from pathlib import Path

from core.harness.knowledge.domain_router import DomainRouter

TARGETS = [
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/harness/knowledge/wiki_quality_monitor.py",
    "aiPlat-core/core/harness/knowledge/skill_marketplace.py",
    "aiPlat-core/core/harness/knowledge/sqlite_retriever.py",
    "aiPlat-platform/kb/service.py",
]


def test_platform_collection_profile_helpers():
    assert DomainRouter.PLATFORM_DEFAULT_COLLECTION == "default"
    assert DomainRouter.PLATFORM_DEFAULT_PROFILE == "default"
    assert DomainRouter.default_collection() == "default"
    assert DomainRouter.default_profile() == "default"


def test_targets_use_collection_or_profile_ssot():
    for rel in TARGETS:
        text = Path(rel).read_text(encoding="utf-8")
        assert (
            "default_collection()" in text or "default_profile()" in text
        ), rel
        assert 'collection_id: str = "default"' not in text, rel
        assert 'profile_id: str = "default"' not in text, rel


def test_production_collection_profile_defaults_empty():
    rx = re.compile(
        r"(collection_id|profile_id)\s*:\s*str\s*=\s*[\"']default[\"']"
        r"|(collection_id|profile_id)\s*=\s*[\"']default[\"']"
        r"|(collection_id|profile_id)[^\n]*DEFAULT\s+'default'"
    )
    hits = []
    for root in (Path("aiPlat-core/core"), Path("aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln) and "DomainRouter.default_" not in ln:
                    hits.append(f"{p}:{i}:{ln.strip()}")
    assert hits == [], hits
