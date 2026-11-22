"""N07/N22 deepen：H.1 condition $and/$or 深度 2；非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_bool_depth2():
    attrs = {"status": "open", "tier": "gold", "region": "cn"}
    # $and 内嵌 $or
    assert (
        match_abox_condition(
            {
                "$and": [
                    {"status": "open"},
                    {"$or": [{"tier": "gold"}, {"tier": "platinum"}]},
                ]
            },
            attrs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {
                "$and": [
                    {"status": "open"},
                    {"$or": [{"tier": "bronze"}, {"tier": "silver"}]},
                ]
            },
            attrs,
        )
        is False
    )
    # $or 内嵌 $and
    assert (
        match_abox_condition(
            {
                "$or": [
                    {"status": "closed"},
                    {"$and": [{"tier": "gold"}, {"region": "cn"}]},
                ]
            },
            attrs,
        )
        is True
    )
    # 深度 3 → 拒配
    assert (
        match_abox_condition(
            {
                "$and": [
                    {
                        "$or": [
                            {"$and": [{"status": "open"}]},
                        ]
                    }
                ]
            },
            attrs,
        )
        is False
    )
    # 嵌套 $not → 见 not-bool-depth2；本文件只锁定深度 3 拒配


def test_check_entity_acl_bool_depth2_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d2"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={
            "$and": [
                {"status": "open"},
                {"$or": [{"tier": {"$gte": "gold"}}, {"vip": True}]},
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


def test_panel_documents_bool_depth2():
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
    assert "深度" in text or "depth" in text.lower() or "嵌套" in text
    assert "非表达式语言" in text
