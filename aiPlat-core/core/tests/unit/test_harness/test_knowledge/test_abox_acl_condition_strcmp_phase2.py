"""N07/N22 deepen：H.1 condition 字符串字典序 $gt/$gte/$lt/$lte；非嵌套布尔 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_strcmp_ops():
    assert match_abox_condition({"tier": {"$gt": "a"}}, {"tier": "b"}) is True
    assert match_abox_condition({"tier": {"$gt": "b"}}, {"tier": "a"}) is False
    assert match_abox_condition({"tier": {"$gte": "b"}}, {"tier": "b"}) is True
    assert match_abox_condition({"tier": {"$lt": "b"}}, {"tier": "a"}) is True
    assert match_abox_condition({"tier": {"$lte": "b"}}, {"tier": "b"}) is True
    # 混合类型 / bool / 缺失 → 不匹配（数值路径仍独立）
    assert match_abox_condition({"tier": {"$gt": "a"}}, {"tier": 2}) is False
    assert match_abox_condition({"tier": {"$gt": 1}}, {"tier": "2"}) is False
    assert match_abox_condition({"score": {"$gt": 10}}, {"score": 11}) is True
    assert match_abox_condition({"tier": {"$gt": "a"}}, {"name": "x"}) is False
    assert match_abox_condition({"tier": {"$gt": "a"}}, {"tier": True}) is False


def test_check_entity_acl_strcmp_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-strcmp"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"tier": {"$gte": "gold"}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"tier": "platinum"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"tier": "bronze"}) is True


def test_panel_documents_strcmp():
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
    assert "字典序" in text
    assert "非表达式语言" in text
