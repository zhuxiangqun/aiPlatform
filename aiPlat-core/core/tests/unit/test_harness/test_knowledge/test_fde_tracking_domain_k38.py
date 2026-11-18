"""N09 K38 — platform FDE API tracking domain via DomainRouter."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


API = (_repo_root() / "aiPlat-platform/apps/fde/api")


def test_platform_fde_api_no_hardcoded_fde_delivery_loads():
    bare = []
    for py in sorted(API.glob("*.py")):
        if py.name == "graph_tenant.py":
            continue
        for i, ln in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if 'GraphIndex.load("fde-delivery"' in ln or "list_branches(\"fde-delivery\"" in ln:
                bare.append(f"{py.name}:{i}")
    assert bare == [], bare


def test_fde_graph_domain_uses_tracking_domain(monkeypatch):
    from apps.fde.api import graph_tenant as gt

    class _R:
        PLATFORM_TRACKING_DOMAIN = "fde-delivery"

        def tracking_domain(self):
            return "tracking-from-router"

    monkeypatch.setattr(
        "core.api.core_facade.get_domain_router",
        lambda: _R(),
    )
    assert gt.fde_graph_domain() == "tracking-from-router"


def test_graph_tenant_module_exports_domain_helper():
    text = (_repo_root() / "aiPlat-platform/apps/fde/api/graph_tenant.py").read_text(encoding="utf-8")
    assert "def fde_graph_domain(" in text
    assert "get_domain_router" in text
    assert "from core.harness" not in text


def test_sessions_v2_loads_via_fde_graph_domain():
    text = (_repo_root() / "aiPlat-platform/apps/fde/api/fde_sessions_v2.py").read_text(encoding="utf-8")
    assert "GraphIndex.load(fde_graph_domain(), tenant_id=fde_graph_tenant())" in text
    assert text.count("GraphIndex.load(fde_graph_domain()") >= 5
