"""N07/N22 deepen：H.1 condition $all；有界期望集 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_all():
    attrs = {"tags": ["a", "b", "c"], "status": "open"}
    assert match_abox_condition({"tags": {"$all": ["a", "b"]}}, attrs) is True
    assert match_abox_condition({"tags": {"$all": ["a", "z"]}}, attrs) is False
    # 空期望 ≡ 空真（主语仍须为集合）
    assert match_abox_condition({"tags": {"$all": []}}, attrs) is True
    assert match_abox_condition({"status": {"$all": []}}, attrs) is False
    # 非 list 期望 / 超长期望 → 拒配
    assert match_abox_condition({"tags": {"$all": "a"}}, attrs) is False
    assert match_abox_condition({"tags": {"$all": [str(i) for i in range(33)]}}, attrs) is False
    # $in 回归
    assert match_abox_condition({"status": {"$in": ["open"]}}, attrs) is True


def test_check_entity_acl_all_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-all"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"tags": {"$all": ["secret", "pii"]}},
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"tags": ["secret", "pii", "x"]}
        )
        is False
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"tags": ["secret"]}
        )
        is True
    )


def test_panel_documents_all():
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
    assert "$all" in text
    assert "非表达式语言" in text
