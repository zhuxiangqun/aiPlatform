"""N07/N22 deepen：H.1 condition $eq/$ne/$in；非表达式语言 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import (
    check_entity_acl,
    match_abox_condition,
    set_entity_acl,
)


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_ops_eq_ne_in():
    assert match_abox_condition({"status": {"$eq": "open"}}, {"status": "open"}) is True
    assert match_abox_condition({"status": {"$ne": "closed"}}, {"status": "open"}) is True
    assert match_abox_condition({"status": {"$ne": "open"}}, {"status": "open"}) is False
    assert match_abox_condition({"status": {"$in": ["open", "pending"]}}, {"status": "pending"}) is True
    assert match_abox_condition({"status": {"$in": ["open"]}}, {"status": "closed"}) is False
    # 非法：多运算符 / 未知算子 → 不匹配
    assert match_abox_condition({"status": {"$eq": "a", "$ne": "b"}}, {"status": "a"}) is False
    assert match_abox_condition({"status": {"$gt": 1}}, {"status": 2}) is False
    # 标量仍等值
    assert match_abox_condition({"status": "open"}, {"status": "open"}) is True


def test_check_entity_acl_with_in_condition(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-ops"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"status": {"$in": ["open", "pending"]}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "open"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "closed"}) is True


def test_abox_panel_documents_ops():
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
    assert "$in" in text
    assert "$ne" in text
    assert "非表达式语言" in text
