"""N09 K39 — FDE terms/atom/kb domains via DomainRouter."""
from __future__ import annotations

from pathlib import Path

API = Path("aiPlat-platform/apps/fde/api")
HARD = ("enterprise-terms", "knowledge-atom", "ai-knowledge", "fde-delivery")


def test_platform_fde_api_no_hardcoded_domain_loads():
    bare = []
    for py in sorted(API.glob("*.py")):
        if py.name == "graph_tenant.py":
            continue
        for i, ln in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if "GraphIndex.load(" not in ln:
                continue
            if any(f'GraphIndex.load("{d}"' in ln for d in HARD):
                bare.append(f"{py.name}:{i}")
    assert bare == [], bare


def test_domain_router_platform_domain_helpers():
    from core.harness.knowledge.domain_router import DomainRouter

    r = DomainRouter()
    assert r.terms_domain() == DomainRouter.PLATFORM_TERMS_DOMAIN
    assert r.knowledge_atom_domain() == DomainRouter.PLATFORM_ATOM_DOMAIN
    assert r.default_kb_domain() == DomainRouter.PLATFORM_KB_DOMAIN


def test_fde_domain_helpers_delegate(monkeypatch):
    from apps.fde.api import graph_tenant as gt

    class _R:
        PLATFORM_TERMS_DOMAIN = "enterprise-terms"
        PLATFORM_ATOM_DOMAIN = "knowledge-atom"
        PLATFORM_KB_DOMAIN = "ai-knowledge"

        def terms_domain(self):
            return "terms-from-router"

        def knowledge_atom_domain(self):
            return "atom-from-router"

        def default_kb_domain(self):
            return "kb-from-router"

    monkeypatch.setattr("core.api.core_facade.get_domain_router", lambda: _R())
    assert gt.fde_terms_domain() == "terms-from-router"
    assert gt.fde_atom_domain() == "atom-from-router"
    assert gt.fde_kb_domain() == "kb-from-router"


def test_clarify_dialog_uses_tracking_domain():
    text = Path("aiPlat-core/core/apps/fde/service/clarify_dialog.py").read_text(
        encoding="utf-8"
    )
    assert 'GraphIndex.load("fde-delivery"' not in text
    assert "tracking_domain()" in text
