"""N07/N22 deepen：H.1 condition $nin；非完整表达式语言 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_nin_ops():
    assert match_abox_condition({"status": {"$nin": ["closed", "archived"]}}, {"status": "open"}) is True
    assert match_abox_condition({"status": {"$nin": ["open", "pending"]}}, {"status": "open"}) is False
    assert match_abox_condition({"status": {"$nin": []}}, {"status": "open"}) is True
    # 非 list → 拒配；$in 回归
    assert match_abox_condition({"status": {"$nin": "open"}}, {"status": "x"}) is False
    assert match_abox_condition({"status": {"$in": ["open"]}}, {"status": "open"}) is True


def test_check_entity_acl_nin_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-nin"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"status": {"$nin": ["archived"]}},
    )
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "open"}) is False
    assert check_entity_acl(domain, "e1", "viewer", "read", attrs={"status": "archived"}) is True


def test_panel_documents_nin():
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
    assert "$nin" in text
    assert "非表达式语言" in text
