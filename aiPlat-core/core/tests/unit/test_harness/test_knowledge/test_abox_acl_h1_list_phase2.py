"""N07/N22 deepen：H.1 list_h1_policies 薄导出；非完整策略编辑器 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import apply_h1_policy, list_h1_policies


ROOT = Path(__file__).resolve().parents[6]


def test_list_h1_policies_sorted(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-h1-list"
    apply_h1_policy(
        domain,
        "b-ent",
        {"effect": "allow", "principals": ["role:analyst"], "actions": ["read"]},
    )
    apply_h1_policy(
        domain,
        "a-ent",
        {
            "effect": "deny",
            "principals": ["role:viewer"],
            "actions": ["read"],
            "masked_properties": ["ssn"],
        },
    )
    policies = list_h1_policies(domain)
    assert [p["resource"] for p in policies] == ["a-ent", "b-ent"]
    assert policies[0]["effect"] == "deny"
    assert policies[0]["masked_properties"] == ["ssn"]
    assert policies[0]["certified"] is False
    assert policies[1]["effect"] == "allow"


def test_get_routes_and_panel_wire_h1_list():
    routes = (
        ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "action_routes.py"
    ).read_text(encoding="utf-8")
    assert "list_graph_h1_policies" in routes
    assert '/graph/acl/{domain_id}/h1' in routes or "/graph/acl/{domain_id}/h1" in routes
    assert "h1_policies" in routes
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "h1_policies" in panel or "h1Policies" in panel
    assert "刷新 H.1 列表" in panel
    assert "/h1" in panel


def test_facade_exports_list_graph_h1_policies():
    from core.api import core_facade as facade

    assert hasattr(facade, "list_graph_h1_policies")
