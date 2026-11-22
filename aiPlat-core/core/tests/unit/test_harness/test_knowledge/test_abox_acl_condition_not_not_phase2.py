"""N07/N22 deepen：H.1 $not→$not 正规求值再取反；有界 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_not_not():
    attrs = {"status": "open", "tier": "gold"}
    # 双重否定字段 → 等价字段命中
    assert (
        match_abox_condition({"$not": {"$not": {"status": "open"}}}, attrs) is True
    )
    assert (
        match_abox_condition({"$not": {"$not": {"status": "closed"}}}, attrs) is False
    )
    # $not→$not→$or
    assert (
        match_abox_condition(
            {"$not": {"$not": {"$or": [{"status": "closed"}, {"tier": "gold"}]}}},
            attrs,
        )
        is True
    )
    # 超深 $not 链拒配（深度 ≤15 → 十六层 $not 拒配）
    deep = {"status": "open"}
    for _ in range(16):
        deep = {"$not": deep}
    assert match_abox_condition(deep, attrs) is False


def test_check_entity_acl_not_not_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-not-not"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"$not": {"$not": {"status": "open"}}},
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"status": "open"}
        )
        is False
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"status": "closed"}
        )
        is True
    )


def test_panel_documents_not_not():
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
