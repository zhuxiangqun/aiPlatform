"""N07/N22 deepen：H.1 condition $and/$or 深度 7；拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def _depth7_tree(*, env_value: str) -> dict:
    """$and→$or→$and→$or→$and→$or→$and（深度 7）。"""
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
                                                            {"env": env_value},
                                                            {"lane": "x"},
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


def test_match_condition_bool_depth7():
    attrs = {
        "status": "open",
        "tier": "gold",
        "region": "cn",
        "env": "prod",
        "lane": "x",
    }
    assert match_abox_condition(_depth7_tree(env_value="prod"), attrs) is True
    assert match_abox_condition(_depth7_tree(env_value="dev"), attrs) is False
    # 深度 8 → 拒配（None 传播，外层不可 fail-open）
    assert (
        match_abox_condition(
            {
                "$and": [
                    {
                        "$or": [
                            {
                                "$and": [
                                    {
                                        "$or": [
                                            {
                                                "$and": [
                                                    {
                                                        "$or": [
                                                            {
                                                                "$and": [
                                                                    {
                                                                        "$or": [
                                                                            {
                                                                                "$and": [
                                                                                    {
                                                                                        "status": "open"
                                                                                    }
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
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            attrs,
        )
        is False
    )
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
                                                        {
                                                            "$or": [
                                                                {
                                                                    "$and": [
                                                                        {
                                                                            "$or": [
                                                                                {
                                                                                    "$and": [
                                                                                        {
                                                                                            "status": "closed"
                                                                                        }
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


def test_check_entity_acl_bool_depth7_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d7"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition=_depth7_tree(env_value="prod"),
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
                "env": "dev",
                "lane": "x",
            },
        )
        is True
    )


def test_panel_documents_bool_depth7():
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
    assert "深度≤7" in text or "深度 ≤7" in text or "深度<=7" in text
    assert "非表达式语言" in text
