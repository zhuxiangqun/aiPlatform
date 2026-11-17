"""N09 K31 — platform FDE API GraphIndex tenant (wave 1)."""
from __future__ import annotations

from pathlib import Path

_FILES = (
    "aiPlat-platform/apps/fde/api/action_routes.py",
    "aiPlat-platform/apps/fde/api/fde_ask.py",
    "aiPlat-platform/apps/fde/api/fde_delivery.py",
    "aiPlat-platform/apps/fde/api/fde_dashboard_v2.py",
    "aiPlat-platform/apps/fde/api/fde_trends.py",
    "aiPlat-platform/apps/fde/api/fde_sessions_compare.py",
    "aiPlat-platform/apps/fde/api/fde_governance.py",
    "aiPlat-platform/apps/fde/api/rapid_insight.py",
)


def _assert_no_bare_loads(rel: str) -> None:
    text = Path(rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_k31_wave_sources_wire_tenant():
    helper = Path("aiPlat-platform/apps/fde/api/graph_tenant.py").read_text(
        encoding="utf-8"
    )
    assert "def fde_graph_tenant(" in helper
    for rel in _FILES:
        text = Path(rel).read_text(encoding="utf-8")
        assert "fde_graph_tenant" in text, rel
        _assert_no_bare_loads(rel)


def test_fde_graph_tenant_prefers_request(monkeypatch):
    from apps.fde.api import graph_tenant as gt

    helper = Path("aiPlat-platform/apps/fde/api/graph_tenant.py").read_text(
        encoding="utf-8"
    )
    # 为什么：身份失败必须可观测，禁止静默吞错回归
    assert "logger.debug(" in helper
    assert "exc_info=True" in helper
    assert "from core.api.core_facade import resolve_graph_tenant" in helper
    assert "from core.harness" not in helper

    monkeypatch.setattr(
        "auth.request_identity.resolve_request_tenant",
        lambda request: "n09-t31-req",
    )
    monkeypatch.setattr(
        "core.api.core_facade.resolve_graph_tenant",
        lambda params=None: "n09-t31-ctx",
    )
    assert gt.fde_graph_tenant(object()) == "n09-t31-req"
    assert gt.fde_graph_tenant(None) == "n09-t31-ctx"
