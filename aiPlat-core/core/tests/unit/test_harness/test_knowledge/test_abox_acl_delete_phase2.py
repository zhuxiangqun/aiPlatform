"""N07/N22 deepen：ABox ACL DELETE + 薄 UI 删除；非 certified / 非全量权限产品。"""
from __future__ import annotations

import inspect
from pathlib import Path

from core.policy.graph_abox_acl import (
    load_abox_acl,
    remove_entity_acl,
    remove_field_acl,
    set_entity_acl,
    set_field_acl,
)


ROOT = Path(__file__).resolve().parents[6]  # workspace root


def test_remove_entity_and_field_acl_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-del"
    set_entity_acl(domain, "e1", deny_roles={"viewer": ["read"]})
    set_field_acl(domain, "e1", "ssn", visibility="role:admin", redaction="mask")
    assert "e1" in load_abox_acl(domain)["entities"]
    assert "e1.ssn" in load_abox_acl(domain)["fields"]
    assert remove_field_acl(domain, "e1", "ssn") is True
    assert "e1.ssn" not in load_abox_acl(domain)["fields"]
    assert remove_entity_acl(domain, "e1") is True
    assert "e1" not in load_abox_acl(domain)["entities"]
    assert remove_entity_acl(domain, "e1") is False
    assert remove_field_acl(domain, "e1", "ssn") is False


def test_facade_remove_graph_acl_symbols():
    from core.api import core_facade as facade

    assert callable(facade.remove_graph_entity_acl)
    assert callable(facade.remove_graph_field_acl)


def test_delete_routes_exist_and_honesty():
    from apps.fde.api import action_routes as mod

    assert hasattr(mod, "delete_graph_entity_acl")
    assert hasattr(mod, "delete_graph_field_acl")
    assert "certified" in inspect.getsource(mod.delete_graph_entity_acl)
    assert "remove_graph_entity_acl" in inspect.getsource(mod.delete_graph_entity_acl)
    assert "remove_graph_field_acl" in inspect.getsource(mod.delete_graph_field_acl)


def test_abox_panel_wires_delete():
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
    assert "method: 'DELETE'" in text
    assert "removeEntity" in text
    assert "removeField" in text
