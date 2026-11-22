"""N07/N22 deepen：ABox 实例 ACL 管理端薄 UI；非 certified / 非全量权限产品。"""
from __future__ import annotations

import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]  # workspace root


def test_get_graph_acl_returns_certified_false():
    from apps.fde.api import action_routes as mod

    src = inspect.getsource(mod.get_graph_acl)
    assert "certified" in src
    assert "False" in src
    assert "get_abox_acl_doc" in src


def test_put_graph_entity_and_field_acl_exist():
    from apps.fde.api import action_routes as mod

    assert hasattr(mod, "put_graph_entity_acl")
    assert hasattr(mod, "put_graph_field_acl")
    assert "set_graph_entity_acl" in inspect.getsource(mod.put_graph_entity_acl)
    assert "set_graph_field_acl" in inspect.getsource(mod.put_graph_field_acl)


def test_abox_acl_panel_wires_api_and_honesty():
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    )
    text = panel.read_text(encoding="utf-8")
    assert "/api/platform/apps/fde" in text
    assert "/graph/acl/" in text
    assert "certified" in text
    assert "非 certified" in text


def test_knowledge_factory_mounts_abox_acl_panel():
    page = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "KnowledgeFactoryPage.tsx"
    )
    text = page.read_text(encoding="utf-8")
    assert "AboxAclPanel" in text
    assert "<AboxAclPanel" in text
