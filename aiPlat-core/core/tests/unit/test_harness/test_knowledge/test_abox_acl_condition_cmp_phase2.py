"""N07/N22 deepen：H.1 condition $gt/$gte/$lt/$lte；非表达式语言 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_cmp_ops():
    assert match_abox_condition({"score": {"$gt": 10}}, {"score": 11}) is True
    assert match_abox_condition({"score": {"$gt": 10}}, {"score": 10}) is False
    assert match_abox_condition({"score": {"$gte": 10}}, {"score": 10}) is True
    assert match_abox_condition({"score": {"$lt": 10}}, {"score": 9}) is True
    assert match_abox_condition({"score": {"$lte": 10}}, {"score": 10}) is True
    # 非数字 / bool / 缺失 → 不匹配
    assert match_abox_condition({"score": {"$gt": 0}}, {"score": "11"}) is False
    assert match_abox_condition({"score": {"$gt": 0}}, {"score": True}) is False
    assert match_abox_condition({"score": {"$gt": 0}}, {"name": "x"}) is False
    # 可与 $exists 同文档多键
    assert (
        match_abox_condition(
            {"score": {"$gte": 5}, "ssn": {"$exists": True}},
            {"score": 5, "ssn": "1"},
        )
        is True
    )


def test_check_entity_acl_cmp_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-cmp"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"score": {"$gt": 80}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"score": 90}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"score": 80}) is True


def test_panel_documents_cmp():
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
    assert "$gt" in text
    assert "$lte" in text
    assert "非表达式语言" in text
