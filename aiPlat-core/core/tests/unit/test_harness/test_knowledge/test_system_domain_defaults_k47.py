"""N09 K47 — aiplat-system signature default via DomainRouter.system_domain()."""
from __future__ import annotations

import re
from pathlib import Path

from core.harness.knowledge.domain_router import DomainRouter


def test_platform_system_constant_and_helper():
    assert DomainRouter.PLATFORM_SYSTEM_DOMAIN == "aiplat-system"
    assert DomainRouter.system_domain() == "aiplat-system"


def test_wiki_generate_domain_uses_system_domain():
    text = Path("aiPlat-core/core/api/routers/wiki.py").read_text(encoding="utf-8")
    assert "DomainRouter.system_domain()" in text
    assert 'domain_id: str = "aiplat-system"' not in text


def test_production_aiplat_system_signature_defaults_empty():
    rx = re.compile(r'domain_id\s*:\s*str\s*=\s*["\']aiplat-system["\']')
    hits = []
    for root in (Path("aiPlat-core/core"), Path("aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p}:{i}")
    assert hits == [], hits
