"""N07/N22 deepen：H.1 condition $and/$or 深度 11；拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def _depth11_tree(*, ch_value: str) -> dict:
    """交替 $and/$or 至深度 11。"""
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
                                                                                    {
                                                                                        "$and": [
                                                                                            {"ch": ch_value},
                                                                                            {"zone": "1"},
                                                                                        ]
                                                                                    },
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


def test_match_condition_bool_depth11():
    attrs = {
        "status": "open",
        "tier": "gold",
        "region": "cn",
        "env": "prod",
        "lane": "x",
        "ch": "a",
        "zone": "1",
    }
    assert match_abox_condition(_depth11_tree(ch_value="a"), attrs) is True
    assert match_abox_condition(_depth11_tree(ch_value="b"), attrs) is False
    deep12 = {"status": "open"}
    for op in ("$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and"):
        deep12 = {op: [deep12]}
    assert match_abox_condition(deep12, attrs) is False
    deep12_closed = {"status": "closed"}
    for op in ("$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or"):
        deep12_closed = {op: [deep12_closed]}
    assert match_abox_condition({"$not": deep12_closed}, attrs) is False


def test_check_entity_acl_bool_depth11_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d11"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition=_depth11_tree(ch_value="a"),
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
                "zone": "1",
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
                "zone": "1",
            },
        )
        is True
    )


def test_panel_documents_bool_depth11():
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
    assert "深度≤11" in text or "深度 ≤11" in text or "深度<=11" in text
    assert "非表达式语言" in text
