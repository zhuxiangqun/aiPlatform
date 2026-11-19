"""N09 K41 — competition domain via DomainRouter (rapid_insight)."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


RI = (_repo_root() / "aiPlat-core/core/apps/fde/service/rapid_insight_service.py")


def test_domain_router_competition_domain():
    from core.harness.knowledge.domain_router import DomainRouter

    r = DomainRouter()
    assert r.competition_domain() == DomainRouter.PLATFORM_COMPETITION_DOMAIN
    assert r.competition_domain() == "bell-competition"


def test_rapid_insight_no_hardcoded_competition_graphindex_load():
    text = RI.read_text(encoding="utf-8")
    assert 'GraphIndex.load("bell-competition"' not in text
    assert "GraphIndex.load('bell-competition'" not in text
    assert "_ri_competition_domain()" in text
    assert "competition_domain()" in text


def test_rapid_insight_competition_membership_uses_helper():
    text = RI.read_text(encoding="utf-8")
    assert 'if "bell-competition" in aligned_domains' not in text
    assert "comp_domain in aligned_domains" in text


def test_production_graphindex_load_literals_empty():
    import re

    rx = re.compile(r'GraphIndex\.load\(\s*["\']([a-z0-9_-]+)["\']')
    hits = []
    for root in ((_repo_root() / "aiPlat-core/core"), (_repo_root() / "aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                m = rx.search(ln)
                if m:
                    hits.append(f"{p}:{i}:{m.group(1)}")
    assert hits == [], hits
