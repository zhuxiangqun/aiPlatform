"""N07/N22 deepen：字段 ACL 管理端薄 UI + list API；非 certified / 非全量权限产品。"""
from __future__ import annotations

import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]  # workspace root


def test_list_field_permissions_endpoint_exists():
    from core.api.routers import wiki_field_security as mod

    assert hasattr(mod, "list_field_permissions")
    src = inspect.getsource(mod.list_field_permissions)
    assert "certified" in src
    assert "load_field_permissions" in src


def test_list_route_registered_before_entity_path():
    from core.api.routers import wiki_field_security as mod

    src = inspect.getsource(mod)
    list_idx = src.find('@router.get("/field-permissions"')
    entity_idx = src.find('@router.get("/field-permissions/{entity_uri:path}"')
    assert list_idx >= 0 and entity_idx > list_idx


def test_field_acl_panel_wires_api_and_honesty():
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "FieldAclPanel.tsx"
    )
    text = panel.read_text(encoding="utf-8")
    assert "/api/core/wiki/ontology/field-permissions" in text
    assert "certified" in text
    assert "非 certified" in text


def test_knowledge_factory_mounts_field_acl_panel():
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
    assert "FieldAclPanel" in text
    assert "<FieldAclPanel" in text
