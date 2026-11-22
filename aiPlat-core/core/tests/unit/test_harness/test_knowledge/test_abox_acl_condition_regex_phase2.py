"""N07/N22 deepen：H.1 condition $regex；有界模式 / 非表达式语言 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_regex_ops():
    assert match_abox_condition({"code": {"$regex": r"^LS-"}}, {"code": "LS-001"}) is True
    assert match_abox_condition({"code": {"$regex": r"^LS-"}}, {"code": "XX-001"}) is False
    # 缺失 / 非 str 模式 / 过长 / 非法正则 → 不匹配
    assert match_abox_condition({"code": {"$regex": r"^LS-"}}, {"name": "x"}) is False
    assert match_abox_condition({"code": {"$regex": 123}}, {"code": "LS-001"}) is False
    assert match_abox_condition({"code": {"$regex": "a" * 129}}, {"code": "a"}) is False
    assert match_abox_condition({"code": {"$regex": "("}}, {"code": "("}) is False
    # 可与数值比较同文档多键
    assert (
        match_abox_condition(
            {"code": {"$regex": r"^LS-"}, "score": {"$gte": 5}},
            {"code": "LS-9", "score": 5},
        )
        is True
    )


def test_check_entity_acl_regex_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-regex"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"code": {"$regex": r"^SEC-"}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"code": "SEC-9"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"code": "PUB-1"}) is True


def test_panel_documents_regex():
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
    assert "$regex" in text
    assert "非表达式语言" in text
