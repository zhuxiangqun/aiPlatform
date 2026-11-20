"""N07/N22 deepen：H.1 condition 浅层 $and/$or；无 $not / 非嵌套 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_bool_shallow():
    attrs = {"status": "open", "tier": "gold"}
    assert (
        match_abox_condition(
            {"$and": [{"status": "open"}, {"tier": {"$gte": "gold"}}]},
            attrs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {"$and": [{"status": "open"}, {"tier": {"$gte": "platinum"}}]},
            attrs,
        )
        is False
    )
    assert (
        match_abox_condition(
            {"$or": [{"status": "closed"}, {"tier": {"$gte": "gold"}}]},
            attrs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {"$or": [{"status": "closed"}, {"tier": "bronze"}]},
            attrs,
        )
        is False
    )
    # 嵌套 / 混用字段键 / 空列表 / 超长 / $not → 拒配
    assert (
        match_abox_condition(
            {"$and": [{"$or": [{"status": "open"}]}]},
            attrs,
        )
        is False
    )
    assert match_abox_condition({"$and": [{"status": "open"}], "x": 1}, attrs) is False
    assert match_abox_condition({"$and": []}, attrs) is False
    assert match_abox_condition({"$and": [{"status": "open"}] * 9}, attrs) is False
    assert match_abox_condition({"$not": [{"status": "open"}]}, attrs) is False


def test_check_entity_acl_bool_shallow_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"$or": [{"status": "open"}, {"tier": {"$gte": "gold"}}]},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "open"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "closed", "tier": "bronze"}) is True


def test_panel_documents_bool_shallow():
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
    assert "$and" in text
    assert "$or" in text
    assert "非表达式语言" in text
