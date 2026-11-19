"""N09 K47 — aiplat-system signature default via DomainRouter.system_domain()."""
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


def test_platform_system_constant_and_helper():
    assert DomainRouter.PLATFORM_SYSTEM_DOMAIN == "aiplat-system"
    assert DomainRouter.system_domain() == "aiplat-system"


def test_wiki_generate_domain_uses_system_domain():
    text = (_repo_root() / "aiPlat-core/core/api/routers/wiki.py").read_text(encoding="utf-8")
    assert "DomainRouter.system_domain()" in text
    assert 'domain_id: str = "aiplat-system"' not in text


def test_production_aiplat_system_signature_defaults_empty():
    rx = re.compile(r'domain_id\s*:\s*str\s*=\s*["\']aiplat-system["\']')
    hits = []
    for root in ((_repo_root() / "aiPlat-core/core"), (_repo_root() / "aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p}:{i}")
    assert hits == [], hits
