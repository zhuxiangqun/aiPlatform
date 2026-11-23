"""N07/N22 deepen：H.1 有界表达式切片 C（字段级 $not；正规求值再取反 / 禁 fail-open）。

非 $where/$expr / 非 certified / 非嵌套字段 $not。
"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_field_not():
    attrs = {"score": 3, "name": "alice", "tags": ["a", "b"]}
    assert match_abox_condition({"score": {"$not": {"$gt": 5}}}, attrs) is True
    assert match_abox_condition({"score": {"$not": {"$gt": 1}}}, attrs) is False
    assert match_abox_condition({"name": {"$not": {"$eq": "bob"}}}, attrs) is True
    assert match_abox_condition({"name": {"$not": {"$regex": "ali"}}}, attrs) is False
    assert match_abox_condition({"tags": {"$not": {"$size": 2}}}, attrs) is False
    assert match_abox_condition({"tags": {"$not": {"$size": 3}}}, attrs) is True
    assert match_abox_condition({"score": {"$not": {"$type": "string"}}}, attrs) is True
    # 形态拒配：不 fail-open
    assert match_abox_condition({"score": {"$not": {}}}, attrs) is False
    assert match_abox_condition({"score": {"$not": {"$gt": 5, "$lt": 10}}}, attrs) is False
    assert (
        match_abox_condition(
            {"score": {"$not": {"$not": {"$eq": 3}}}},
            attrs,
        )
        is False
    )
    assert (
        match_abox_condition(
            {"score": {"$not": {"$or": [{"$eq": 3}]}}},
            attrs,
        )
        is False
    )
    assert match_abox_condition({"score": {"$not": {"$type": "bson"}}}, attrs) is False
    assert match_abox_condition({"name": {"$not": {"$regex": "(("}}}, attrs) is False
    # A+B 回归：点号 + $not
    nested = {"profile": {"tier": "gold"}}
    assert (
        match_abox_condition({"profile.tier": {"$not": {"$eq": "silver"}}}, nested)
        is True
    )


def test_check_entity_acl_field_not_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-expr-c"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"score": {"$not": {"$lt": 10}}},
    )
    # score=12 → not (12<10) → True → deny 生效
    assert (
        check_entity_acl(domain, "e1", "viewer", "read", attrs={"score": 12}) is False
    )
    # score=3 → not (3<10) → False → condition 不命中 → 放行
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"score": 3}) is True


def test_panel_documents_expr_lang_c():
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
    assert "字段级 $not" in text
    assert "非表达式语言" in text
    assert "非 $where/$expr" in text
