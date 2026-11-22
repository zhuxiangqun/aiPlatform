"""N07/N22 deepen：H.1 condition $and/$or 深度 5；拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_bool_depth5():
    attrs = {"status": "open", "tier": "gold", "region": "cn", "env": "prod", "ch": "a"}
    # 深度 5：$and→$or→$and→$or→$and
    assert (
        match_abox_condition(
            {
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
                                                    {"env": "prod"},
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
            },
            attrs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {
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
                                                    {"env": "dev"},
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
            },
            attrs,
        )
        is False
    )
    # 深度 6+ 拒配见 bool_depth6；本切片只验深度 5 命中
    # 为什么：超深拒配不可被外层 $not 取反（禁 fail-open）— 深度 7 树
    assert (
        match_abox_condition(
            {
                "$not": {
                    "$and": [
                        {
                            "$or": [
                                {
                                    "$and": [
                                        {
                                            "$or": [
                                                {
                                                    "$and": [
                                                        {"$or": [{"status": "open"}]},
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            },
            attrs,
        )
        is False
    )


def test_check_entity_acl_bool_depth5_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d5"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={
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
                                                {"env": "prod"},
                                            ]
                                        },
                                        {"region": "hk"},
                                    ]
                                },
                            ]
                        },
                        {"vip": True},
                    ]
                },
            ]
        },
    )
    assert (
        check_entity_acl(
            domain,
            "e1",
            "viewer",
            "read",
            attrs={"status": "open", "tier": "gold", "region": "cn", "env": "prod"},
        )
        is False
    )
    assert (
        check_entity_acl(
            domain,
            "e1",
            "viewer",
            "read",
            attrs={"status": "open", "tier": "gold", "region": "cn", "env": "dev"},
        )
        is True
    )


def test_panel_documents_bool_depth5():
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
    assert "深度≤" in text or "深度 ≤" in text or "深度<=" in text
    assert "非表达式语言" in text
