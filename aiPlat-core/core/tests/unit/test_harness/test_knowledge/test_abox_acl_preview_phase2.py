"""N07/N22 deepen：ABox ACL preview-as-role；非 certified / 非 H.1 condition 编辑器。"""
from __future__ import annotations

import inspect
from pathlib import Path

from core.policy.graph_abox_acl import (
    preview_abox_acl,
    set_entity_acl,
    set_field_acl,
)


ROOT = Path(__file__).resolve().parents[6]


def test_preview_abox_acl_deny_and_redact(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-prev"
    set_entity_acl(domain, "e1", deny_roles={"viewer": ["read"]})
    set_field_acl(domain, "e1", "ssn", visibility="role:admin", redaction="replace", replace_with="[X]")
    denied = preview_abox_acl(domain, "e1", {"ssn": "1", "name": "a"}, role="viewer", action="read")
    assert denied["allowed"] is False
    assert denied["certified"] is False
    assert denied["redacted"] == {}
    ok = preview_abox_acl(domain, "e1", {"ssn": "1", "name": "a"}, role="admin", action="read")
    assert ok["allowed"] is True
    assert ok["certified"] is False
    assert ok["redacted"].get("ssn") == "1"  # admin visibility role:admin → visible


def test_preview_facade_and_route():
    from core.api import core_facade as facade
    from apps.fde.api import action_routes as mod

    assert callable(facade.preview_graph_abox_acl)
    assert hasattr(mod, "preview_graph_acl")
    src = inspect.getsource(mod.preview_graph_acl)
    assert "preview_graph_abox_acl" in src
    assert "entity_id_required" in src


def test_abox_panel_wires_preview():
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
    assert "/preview" in text
    assert "runPreview" in text
    assert "非 certified" in text
