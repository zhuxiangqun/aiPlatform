"""N07/N22 deepen：H.1 condition $exists；非表达式语言 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_exists():
    assert match_abox_condition({"ssn": {"$exists": True}}, {"ssn": "1"}) is True
    assert match_abox_condition({"ssn": {"$exists": True}}, {"name": "x"}) is False
    assert match_abox_condition({"ssn": {"$exists": False}}, {"name": "x"}) is True
    assert match_abox_condition({"ssn": {"$exists": False}}, {"ssn": "1"}) is False
    # 与 $in 可同文档多键
    assert (
        match_abox_condition(
            {"ssn": {"$exists": True}, "status": {"$in": ["open"]}},
            {"ssn": "1", "status": "open"},
        )
        is True
    )


def test_check_entity_acl_exists_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-exists"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"ssn": {"$exists": True}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"ssn": "x"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"name": "ok"}) is True


def test_panel_documents_exists():
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "$exists" in panel
