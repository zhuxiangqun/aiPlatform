"""N07/N22 deepen：H.1 condition $and/$or 深度 16；拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def _wrap(depth: int, leaf: dict) -> dict:
    """自内向外包 ``depth`` 层交替布尔。"""
    node: dict = leaf
    for i in range(depth):
        op = "$and" if (depth - i) % 2 == 1 else "$or"
        node = {op: [node]}
    return node


def _depth16_tree(*, rack_value: str) -> dict:
    """交替 $and/$or 至深度 16（depth15 再嵌一层 $or）。"""
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
                                                                                                        "$and": [
                                                                                                            {
                                                                                                                "zone": "1"
                                                                                                            },
                                                                                                            {
                                                                                                                "$or": [
                                                                                                                    {
                                                                                                                        "$and": [
                                                                                                                            {
                                                                                                                                "site": "s1"
                                                                                                                            },
                                                                                                                            {
                                                                                                                                "$or": [
                                                                                                                                    {
                                                                                                                                        "rack": rack_value
                                                                                                                                    },
                                                                                                                                    {
                                                                                                                                        "rack": "rx"
                                                                                                                                    },
                                                                                                                                ]
                                                                                                                            },
                                                                                                                        ]
                                                                                                                    },
                                                                                                                    {
                                                                                                                        "site": "sx"
                                                                                                                    },
                                                                                                                ]
                                                                                                            },
                                                                                                        ]
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


def test_match_condition_bool_depth16():
    attrs = {
        "status": "open",
        "tier": "gold",
        "region": "cn",
        "env": "prod",
        "lane": "x",
        "ch": "a",
        "zone": "1",
        "site": "s1",
        "rack": "r1",
    }
    assert match_abox_condition(_depth16_tree(rack_value="r1"), attrs) is True
    assert match_abox_condition(_depth16_tree(rack_value="r2"), attrs) is False
    assert match_abox_condition(_wrap(17, {"status": "open"}), attrs) is False
    assert (
        match_abox_condition({"$not": _wrap(16, {"status": "closed"})}, attrs) is False
    )


def test_check_entity_acl_bool_depth16_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d16"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition=_depth16_tree(rack_value="r1"),
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
                "site": "s1",
                "rack": "r1",
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
                "zone": "1",
                "site": "s1",
                "rack": "r2",
            },
        )
        is True
    )


def test_panel_documents_bool_depth16():
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
    assert "深度≤16" in text or "深度 ≤16" in text or "深度<=16" in text
    assert "非表达式语言" in text
