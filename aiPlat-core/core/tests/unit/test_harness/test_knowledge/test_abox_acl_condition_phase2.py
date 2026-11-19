"""N07/N22 deepen：H.1 condition 最小等值匹配；非完整策略编辑器 / 非 certified。"""
from __future__ import annotations

import inspect
from pathlib import Path

from core.policy.graph_abox_acl import (
    check_entity_acl,
    match_abox_condition,
    set_entity_acl,
)


ROOT = Path(__file__).resolve().parents[6]


def test_match_abox_condition_basics():
    assert match_abox_condition(None, None) is True
    assert match_abox_condition({}, {"status": "open"}) is True
    assert match_abox_condition({"status": "open"}, None) is False
    assert match_abox_condition({"status": "open"}, {"status": "open"}) is True
    assert match_abox_condition({"status": "open"}, {"status": "closed"}) is False
    assert match_abox_condition({"status": "open"}, {"metadata": {"status": "open"}}) is True


def test_check_entity_acl_condition_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-cond"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"status": "open"},
    )
    # condition 不匹配 → 规则不适用 → 放行
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "closed"}) is True
    # 无 attrs → condition 规则不生效 → 放行（旧路径不误杀）
    assert check_entity_acl(domain, "e1", "viewer", "read") is True
    # 匹配 → deny
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "open"}) is False


def test_object_set_and_facade_wire_condition():
    from core.harness.knowledge_pipeline import object_set as os_mod
    from core.api import core_facade as facade
    from apps.fde.api import action_routes as routes

    assert "attrs=it" in inspect.getsource(os_mod._apply_abox_acl)
    sig = inspect.signature(facade.set_graph_entity_acl)
    assert "condition" in sig.parameters
    assert "condition" in inspect.getsource(routes.put_graph_entity_acl)


def test_abox_panel_wires_condition():
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
    assert "condition" in text
    assert "conditionRaw" in text
