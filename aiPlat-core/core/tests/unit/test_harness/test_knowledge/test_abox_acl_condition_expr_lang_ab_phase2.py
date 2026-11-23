"""N07/N22 deepen：H.1 有界表达式切片 A+B（嵌套 $elemMatch + 布尔谓词 + 点号路径 + $size/$type）。

非 $where/$expr / 非 certified / 非任意深度。
"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import check_entity_acl, match_abox_condition, set_entity_acl


ROOT = Path(__file__).resolve().parents[6]


def test_match_condition_elemmatch_bool_predicate():
    docs = {
        "items": [
            {"status": "closed", "tier": "silver"},
            {"status": "open", "tier": "gold"},
        ],
    }
    assert (
        match_abox_condition(
            {
                "items": {
                    "$elemMatch": {
                        "$or": [
                            {"status": "open", "tier": "gold"},
                            {"status": "pending"},
                        ]
                    }
                }
            },
            docs,
        )
        is True
    )
    assert (
        match_abox_condition(
            {
                "items": {
                    "$elemMatch": {
                        "$and": [
                            {"status": "open"},
                            {"tier": "silver"},
                        ]
                    }
                }
            },
            docs,
        )
        is False
    )
    assert (
        match_abox_condition(
            {
                "items": {
                    "$elemMatch": {
                        "$nor": [{"status": "closed"}, {"status": "open"}],
                    }
                }
            },
            docs,
        )
        is False
    )


def test_match_condition_nested_elemmatch():
    docs = {
        "items": [
            {
                "status": "open",
                "children": [
                    {"code": "x"},
                    {"code": "y", "tags": ["a", "b"]},
                ],
            }
        ],
    }
    assert (
        match_abox_condition(
            {
                "items": {
                    "$elemMatch": {
                        "status": "open",
                        "children": {"$elemMatch": {"code": "y"}},
                    }
                }
            },
            docs,
        )
        is True
    )
    # nest=3 拒配（帽=2）
    assert (
        match_abox_condition(
            {
                "items": {
                    "$elemMatch": {
                        "children": {
                            "$elemMatch": {
                                "tags": {"$elemMatch": {"$eq": "a"}},
                            }
                        }
                    }
                }
            },
            docs,
        )
        is False
    )


def test_match_condition_dotted_path():
    attrs = {
        "profile": {"tenant": {"id": "t1"}},
        "metadata": {"geo": {"region": "cn"}},
        "props": {"flags": {"vip": True}},
    }
    assert match_abox_condition({"profile.tenant.id": "t1"}, attrs) is True
    assert match_abox_condition({"profile.tenant.id": "t2"}, attrs) is False
    assert match_abox_condition({"geo.region": "cn"}, attrs) is True
    assert match_abox_condition({"flags.vip": True}, attrs) is True
    # 空段 / 超段数拒配
    assert match_abox_condition({"a..b": "x"}, {"a": {"b": "x"}}) is False
    deep = {"a": {}}
    cur = deep["a"]
    for i in range(9):
        cur[f"s{i}"] = {}
        cur = cur[f"s{i}"]
    cur["v"] = 1
    path = ".".join(["a"] + [f"s{i}" for i in range(9)] + ["v"])
    assert len(path.split(".")) > 8
    assert match_abox_condition({path: 1}, deep) is False


def test_match_condition_size_and_type():
    attrs = {
        "tags": ["a", "b", "c"],
        "name": "alice",
        "score": 3,
        "ok": True,
        "meta": {"k": 1},
        "missing": None,
    }
    assert match_abox_condition({"tags": {"$size": 3}}, attrs) is True
    assert match_abox_condition({"tags": {"$size": 2}}, attrs) is False
    assert match_abox_condition({"name": {"$size": 1}}, attrs) is False
    assert match_abox_condition({"tags": {"$size": -1}}, attrs) is False
    assert match_abox_condition({"name": {"$type": "string"}}, attrs) is True
    assert match_abox_condition({"score": {"$type": "number"}}, attrs) is True
    assert match_abox_condition({"ok": {"$type": "bool"}}, attrs) is True
    assert match_abox_condition({"tags": {"$type": "array"}}, attrs) is True
    assert match_abox_condition({"meta": {"$type": "object"}}, attrs) is True
    assert match_abox_condition({"missing": {"$type": "null"}}, {"missing": None}) is True
    assert match_abox_condition({"score": {"$type": "string"}}, attrs) is False
    assert match_abox_condition({"score": {"$type": "bson"}}, attrs) is False
    assert (
        match_abox_condition({"score": {"$type": ["string", "number"]}}, attrs) is True
    )


def test_check_entity_acl_expr_lang_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-expr-ab"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition={
            "items": {
                "$elemMatch": {
                    "$and": [
                        {"status": "blocked"},
                        {"meta.level": {"$type": "number"}},
                    ]
                }
            }
        },
    )
    assert (
        check_entity_acl(
            domain,
            "e1",
            "viewer",
            "read",
            attrs={
                "items": [
                    {"status": "ok"},
                    {"status": "blocked", "meta": {"level": 2}},
                ]
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
            attrs={"items": [{"status": "blocked", "meta": {"level": "x"}}]},
        )
        is True
    )


def test_panel_documents_expr_lang_ab():
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
    assert "$size" in text
    assert "$type" in text
    assert "点号路径" in text
    assert "有界表达式" in text
    assert "非表达式语言" in text
    assert "非 $where/$expr" in text
