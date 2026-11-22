"""N07/N22 deepen：H.1 condition $and/$or 深度 10；拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def _depth10_tree(*, ch_value: str) -> dict:
    """交替 $and/$or 至深度 10。"""
    return {
        "$and": [
            {"status": "open"},
            {
                "$or": [
                    {
                        "$and": [
                            {"tier": "gold"},
                            {
                                "$or": [
                                    {
                                        "$and": [
                                            {"region": "cn"},
                                            {
                                                "$or": [
                                                    {
                                                        "$and": [
                                                            {"env": "prod"},
                                                            {
                                                                "$or": [
                                                                    {
                                                                        "$and": [
                                                                            {"lane": "x"},
                                                                            {
                                                                                "$or": [
                                                                                    {"ch": ch_value},
                                                                                    {"ch": "z"},
                                                                                ]
                                                                            },
                                                                        ]
                                                                    },
                                                                    {"lane": "z"},
                                                                ]
                                                            },
                                                        ]
                                                    },
                                                    {"env": "staging"},
                                                ]
                                            },
                                        ]
                                    },
                                    {"region": "hk"},
                                ]
                            },
                        ]
                    },
                    {"tier": "platinum"},
                ]
            },
        ]
    }


def test_match_condition_bool_depth10():
    attrs = {
        "status": "open",
        "tier": "gold",
        "region": "cn",
        "env": "prod",
        "lane": "x",
        "ch": "a",
    }
    assert match_abox_condition(_depth10_tree(ch_value="a"), attrs) is True
    assert match_abox_condition(_depth10_tree(ch_value="b"), attrs) is False
    deep11 = {"status": "open"}
    for op in ("$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or"):
        deep11 = {op: [deep11]}
    assert match_abox_condition(deep11, attrs) is False
    deep11_closed = {"status": "closed"}
    for op in ("$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and"):
        deep11_closed = {op: [deep11_closed]}
    assert match_abox_condition({"$not": deep11_closed}, attrs) is False


def test_check_entity_acl_bool_depth10_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d10"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition=_depth10_tree(ch_value="a"),
    )
    assert (
        check_entity_acl(
            domain,
            "e1",
            "viewer",
            "read",
            attrs={
                "status": "open",
                "tier": "gold",
                "region": "cn",
                "env": "prod",
                "lane": "x",
                "ch": "a",
            },
        )
        is False
    )
    assert (
        check_entity_acl(
            domain,
            "e1",
            "viewer",
            "read",
            attrs={
                "status": "open",
                "tier": "gold",
                "region": "cn",
                "env": "prod",
                "lane": "x",
                "ch": "b",
            },
        )
        is True
    )


def test_panel_documents_bool_depth10():
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
    assert "$and" in text
    assert "深度≤10" in text or "深度 ≤10" in text or "深度<=10" in text
    assert "非表达式语言" in text
