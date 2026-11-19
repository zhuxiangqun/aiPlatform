"""N07/N22 deepen：单实体 H.1 GET；非完整策略编辑器 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import get_graph_h1_policy
from core.policy.graph_abox_acl import apply_h1_policy


ROOT = Path(__file__).resolve().parents[6]


def test_get_graph_h1_policy_and_404(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-h1-get"
    apply_h1_policy(
        domain,
        "Ticket-1",
        {
            "effect": "deny",
            "principals": ["role:viewer"],
            "actions": ["read"],
            "masked_properties": ["ssn"],
        },
    )
    h1 = get_graph_h1_policy(domain, "Ticket-1")
    assert h1["resource"] == "Ticket-1"
    assert h1["effect"] == "deny"
    assert h1["masked_properties"] == ["ssn"]
    assert h1["certified"] is False
    with pytest.raises(KeyError, match="h1_entity_not_found"):
        get_graph_h1_policy(domain, "missing")


def test_route_and_panel_wire_entity_h1_get():
    routes = (
        ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "action_routes.py"
    ).read_text(encoding="utf-8")
    assert "get_graph_h1_policy" in routes
    assert "/entities/{entity_id}/h1" in routes
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "loadH1Entity" in panel
    assert "加载到编辑区" in panel
    assert "加载 H.1" in panel
    assert "/h1" in panel
