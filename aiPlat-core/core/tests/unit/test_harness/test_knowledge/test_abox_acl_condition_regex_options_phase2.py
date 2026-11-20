"""N07/N22 deepen：H.1 condition $regex+$options:i；非 m/s/x / 非表达式语言 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_regex_options_i():
    # 无 options：仍区分大小写
    assert match_abox_condition({"code": {"$regex": r"^ls-"}}, {"code": "LS-001"}) is False
    # $options:i → 忽略大小写
    assert (
        match_abox_condition(
            {"code": {"$regex": r"^ls-", "$options": "i"}},
            {"code": "LS-001"},
        )
        is True
    )
    assert (
        match_abox_condition(
            {"code": {"$regex": r"^ls-", "$options": "i"}},
            {"code": "XX-001"},
        )
        is False
    )
    # 未知 / 非 i flags → 拒配；多余键 → 拒配
    assert (
        match_abox_condition(
            {"code": {"$regex": r"^ls-", "$options": "m"}},
            {"code": "ls-001"},
        )
        is False
    )
    assert (
        match_abox_condition(
            {"code": {"$regex": r"^ls-", "$options": "is"}},
            {"code": "LS-001"},
        )
        is False
    )
    assert (
        match_abox_condition(
            {"code": {"$regex": r"^ls-", "$options": "i", "$eq": "x"}},
            {"code": "LS-001"},
        )
        is False
    )


def test_check_entity_acl_regex_options_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-regex-opts"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"code": {"$regex": r"^sec-", "$options": "i"}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"code": "SEC-9"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"code": "PUB-1"}) is True


def test_panel_documents_regex_options():
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
    assert "$options" in text
    assert "非表达式语言" in text
