"""N07/N22 deepen：H.1 $not 可否定字段或一层 $and/$or；有界 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_not_over_bool():
    attrs = {"status": "open", "tier": "gold", "region": "cn"}
    # $and 内嵌 $not(字段)
    assert (
        match_abox_condition(
            {"$and": [{"status": "open"}, {"$not": {"tier": "bronze"}}]},
            attrs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {"$and": [{"status": "open"}, {"$not": {"tier": "gold"}}]},
            attrs,
        )
        is False
    )
    # 顶层 $not → $or
    assert (
        match_abox_condition(
            {"$not": {"$or": [{"status": "closed"}, {"tier": "bronze"}]}},
            attrs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {"$not": {"$or": [{"status": "open"}, {"tier": "bronze"}]}},
            attrs,
        )
        is False
    )
    # $not → $and 内嵌 $or（深度内正规求值）；命中 → False
    assert (
        match_abox_condition(
            {
                "$not": {
                    "$and": [
                        {"status": "open"},
                        {"$or": [{"tier": "gold"}]},
                    ]
                }
            },
            attrs,
        )
        is False
    )
    # $not→$not 见 not-not 证据；此处保留混键拒配
    assert match_abox_condition({"$not": {"$and": [], "x": 1}}, attrs) is False
    # $not → 纯字段 $and（命中）→ False
    assert (
        match_abox_condition(
            {"$not": {"$and": [{"status": "open"}, {"tier": "gold"}]}},
            attrs,
        )
        is False
    )
    # $not → 纯字段 $and（未全命中）→ True
    assert (
        match_abox_condition(
            {"$not": {"$and": [{"status": "open"}, {"tier": "bronze"}]}},
            attrs,
        )
        is True
    )


def test_check_entity_acl_not_bool_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-not-bool"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={
            "$and": [
                {"status": "open"},
                {"$not": {"tier": "bronze"}},
            ]
        },
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"status": "open", "tier": "gold"}
        )
        is False
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"status": "open", "tier": "bronze"}
        )
        is True
    )


def test_panel_documents_not_bool_depth2():
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
    assert "深度" in text or "嵌套" in text
    assert "非表达式语言" in text
