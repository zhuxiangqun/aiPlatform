"""N07/N22 deepen：H.1 condition $and/$or 深度 24；拒配传播 / 非完整表达式 / 非 certified。"""
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


def _depth24_tree(*, bay_value: str) -> dict:
    """深度 24：``_wrap(24, {bay})``。"""
    return _wrap(24, {"bay": bay_value})


def test_match_condition_bool_depth24():
    attrs = {"bay": "b1", "status": "open"}
    assert match_abox_condition(_depth24_tree(bay_value="b1"), attrs) is True
    assert match_abox_condition(_depth24_tree(bay_value="b2"), attrs) is False
    # 深度 25+ 拒配见 bool_depth25；本切片只验深度 24 命中
    # 为什么：超深拒配不可被外层 $not 取反（禁 fail-open）— 深度 26 树
    assert (
        match_abox_condition({"$not": _wrap(25, {"bay": "b1"})}, attrs) is False
    )


def test_check_entity_acl_bool_depth24_gates_deny(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-bool-d24"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        condition=_depth24_tree(bay_value="b1"),
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"bay": "b1"}
        )
        is False
    )
    assert (
        check_entity_acl(
            domain, "e1", "viewer", "read", attrs={"bay": "b2"}
        )
        is True
    )


def test_panel_documents_bool_depth24():
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
