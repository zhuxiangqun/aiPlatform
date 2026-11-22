"""N07/N22 deepen：H.1 condition $and/$or 深度 12；拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def _depth12_tree(*, zone_value: str) -> dict:
    """交替 $and/$or 至深度 12。"""
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
                                                                                            {"ch": "a"},
                                                                                            {
                                                                                                "$or": [
                                                                                                    {
                                                                                                        "zone": zone_value
                                                                                                    },
                                                                                                    {
                                                                                                        "zone": "9"
                                                                                                    },
                                                                                                ]
                                                                                            },
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


def test_match_condition_bool_depth12():
    attrs = {
        "status": "open",
        "tier": "gold",
        "region": "cn",
        "env": "prod",
        "lane": "x",
        "ch": "a",
        "zone": "1",
    }
    assert match_abox_condition(_depth12_tree(zone_value="1"), attrs) is True
    assert match_abox_condition(_depth12_tree(zone_value="2"), attrs) is False
    deep13 = {"status": "open"}
    for op in (
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
    ):
        deep13 = {op: [deep13]}
    assert match_abox_condition(deep13, attrs) is False
    deep13_closed = {"status": "closed"}
    for op in (
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
        "$or",
        "$and",
    ):
        deep13_closed = {op: [deep13_closed]}
    assert match_abox_condition({"$not": deep13_closed}, attrs) is False


def test_check_entity_acl_bool_depth12_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d12"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition=_depth12_tree(zone_value="1"),
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
                "ch": "a",
                "zone": "2",
            },
        )
        is True
    )


def test_panel_documents_bool_depth12():
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
    assert "深度≤12" in text or "深度 ≤12" in text or "深度<=12" in text
    assert "非表达式语言" in text
