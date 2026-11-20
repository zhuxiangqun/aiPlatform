"""N07/N22 deepen：H.1 condition 浅层 $not；无多层嵌套 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_not_shallow():
    attrs = {"status": "open", "tier": "gold"}
    assert match_abox_condition({"$not": {"status": "closed"}}, attrs) is True
    assert match_abox_condition({"$not": {"status": "open"}}, attrs) is False
    assert match_abox_condition({"$not": {"tier": {"$gte": "platinum"}}}, attrs) is True
    # list 形态 / 空 / 嵌套布尔 / 混字段键 → 拒配
    assert match_abox_condition({"$not": [{"status": "open"}]}, attrs) is False
    assert match_abox_condition({"$not": {}}, attrs) is False
    assert match_abox_condition({"$not": {"$and": [{"status": "open"}]}}, attrs) is False
    assert match_abox_condition({"$not": {"status": "open"}, "x": 1}, attrs) is False
    # $and/$or 仍可用（回归）
    assert (
        match_abox_condition(
            {"$or": [{"status": "closed"}, {"tier": {"$gte": "gold"}}]},
            attrs,
        )
        is True
    )


def test_check_entity_acl_not_shallow_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-not"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"$not": {"status": "archived"}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "open"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "archived"}) is True


def test_panel_documents_not_shallow():
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
    assert "$not" in text
    assert "非表达式语言" in text
