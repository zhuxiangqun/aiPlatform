"""N07/N22 deepen：H.1 condition $nor（≡¬∨）；有界 / 拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_nor():
    attrs = {"status": "open", "tier": "gold"}
    # 两边皆未命中 → $nor True
    assert (
        match_abox_condition(
            {"$nor": [{"status": "closed"}, {"tier": "silver"}]},
            attrs,
        )
        is True
    )
    # 一侧命中 → $nor False
    assert (
        match_abox_condition(
            {"$nor": [{"status": "open"}, {"tier": "silver"}]},
            attrs,
        )
        is False
    )
    # 嵌套：$and + $nor
    assert (
        match_abox_condition(
            {
                "$and": [
                    {"status": "open"},
                    {"$nor": [{"tier": "silver"}, {"tier": "bronze"}]},
                ]
            },
            attrs,
        )
        is True
    )
    # $not → $nor（正规求值再取反；禁 fail-open）
    assert (
        match_abox_condition(
            {"$not": {"$nor": [{"status": "closed"}, {"tier": "silver"}]}},
            attrs,
        )
        is False
    )
    # 空/$nor 非 list → 拒配
    assert match_abox_condition({"$nor": []}, attrs) is False
    assert match_abox_condition({"$nor": {"status": "open"}}, attrs) is False


def test_check_entity_acl_nor_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-nor"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"$nor": [{"status": "closed"}, {"tier": "silver"}]},
    )
    # $nor 命中 → deny 生效
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"status": "open", "tier": "gold"}
        )
        is False
    )
    # $nor 未命中（status=closed 命中子句）→ deny 不触发
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"status": "closed", "tier": "gold"}
        )
        is True
    )


def test_panel_documents_nor():
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
    assert "$nor" in text
    assert "深度≤" in text or "深度 ≤" in text or "深度<=" in text
    assert "非表达式语言" in text
