"""N07/N22 deepen：H.1 condition $elemMatch；有界数组 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_elemmatch():
    docs = {
        "items": [
            {"status": "closed", "tier": "silver"},
            {"status": "open", "tier": "gold"},
        ],
        "tags": ["a", "b", "c"],
    }
    # 文档元素：字段 AND
    assert (
        match_abox_condition(
            {"items": {"$elemMatch": {"status": "open", "tier": "gold"}}},
            docs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {"items": {"$elemMatch": {"status": "open", "tier": "silver"}}},
            docs,
        )
        is False
    )
    # 标量元素：值算子
    assert match_abox_condition({"tags": {"$elemMatch": {"$eq": "b"}}}, docs) is True
    assert match_abox_condition({"tags": {"$elemMatch": {"$eq": "z"}}}, docs) is False
    # 拒配：非数组 / 空谓词 / 布尔算子 / 嵌套 $elemMatch
    assert match_abox_condition({"status": {"$elemMatch": {"$eq": "x"}}}, {"status": "x"}) is False
    assert match_abox_condition({"tags": {"$elemMatch": {}}}, docs) is False
    assert (
        match_abox_condition(
            {"items": {"$elemMatch": {"$or": [{"status": "open"}]}}},
            docs,
        )
        is False
    )
    assert (
        match_abox_condition(
            {"items": {"$elemMatch": {"child": {"$elemMatch": {"$eq": 1}}}}},
            docs,
        )
        is False
    )
    # $all 回归
    assert match_abox_condition({"tags": {"$all": ["a", "b"]}}, docs) is True


def test_check_entity_acl_elemmatch_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-elemmatch"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={"items": {"$elemMatch": {"status": "blocked"}}},
    )
    assert (
        check_entity_acl(
            domain,
            "e1",
            "viewer",
            "read",
            attrs={"items": [{"status": "ok"}, {"status": "blocked"}]},
        )
        is False
    )
    assert (
        check_entity_acl(
            domain,
            "e1",
            "viewer",
            "read",
            attrs={"items": [{"status": "ok"}]},
        )
        is True
    )


def test_panel_documents_elemmatch():
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
    assert "$elemMatch" in text
    assert "非表达式语言" in text
