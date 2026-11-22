"""N07/N22 deepen：H.1 condition $and/$or 深度 8；拒配传播 / 非完整表达式 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def _depth8_tree(*, lane_value: str) -> dict:
    """$and→$or→$and→$or→$and→$or→$and→$or（深度 8）。"""
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
                                                                    {"lane": lane_value},
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


def test_match_condition_bool_depth8():
    attrs = {
        "status": "open",
        "tier": "gold",
        "region": "cn",
        "env": "prod",
        "lane": "x",
    }
    assert match_abox_condition(_depth8_tree(lane_value="x"), attrs) is True
    assert match_abox_condition(_depth8_tree(lane_value="y"), attrs) is False
    # 深度 9 → 拒配（None 传播，外层不可 fail-open）
    deep9 = {"status": "open"}
    for op in ("$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and", "$or"):
        deep9 = {op: [deep9]}
    assert match_abox_condition(deep9, attrs) is False
    # $not + 8 层同族 = 深度 9；叶子 closed 若被 fail-open 取反会变 True
    deep9_closed = {"status": "closed"}
    for op in ("$or", "$and", "$or", "$and", "$or", "$and", "$or", "$and"):
        deep9_closed = {op: [deep9_closed]}
    assert match_abox_condition({"$not": deep9_closed}, attrs) is False


def test_check_entity_acl_bool_depth8_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d8"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition=_depth8_tree(lane_value="x"),
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
                "env": "prod",
                "lane": "y",
            },
        )
        is True
    )


def test_panel_documents_bool_depth8():
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
    assert "深度≤8" in text or "深度 ≤8" in text or "深度<=8" in text
    assert "非表达式语言" in text
