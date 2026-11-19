"""N07/N22 deepen：H.1 apply_h1_policy 薄导入；非完整策略编辑器 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.policy.graph_abox_acl import (
    apply_h1_policy,
    check_entity_acl,
    entity_acl_to_h1,
    list_masked_properties,
    load_abox_acl,
)


ROOT = Path(__file__).resolve().parents[6]


def test_apply_h1_policy_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-h1-apply"
    eid = "Ticket-9"
    entry = apply_h1_policy(
        domain,
        eid,
        {
            "resource": eid,
            "effect": "deny",
            "principals": ["role:viewer"],
            "actions": ["read", "update"],
            "condition": {"status": "open"},
            "masked_properties": ["ssn"],
        },
    )
    assert entry.get("deny_roles", {}).get("viewer") == ["read", "update"]
    assert entry.get("allow_roles") == {}
    assert entry.get("condition") == {"status": "open"}
    assert list_masked_properties(domain, eid) == ["ssn"]
    assert (load_abox_acl(domain).get("fields") or {})[f"{eid}.ssn"]["visibility"] == "none"
    assert check_entity_acl(domain, eid, "viewer", "read", attrs={"status": "open"}) is False
    assert check_entity_acl(domain, eid, "viewer", "read", attrs={"status": "closed"}) is True
    h1 = entity_acl_to_h1(domain, eid)
    assert h1["effect"] == "deny"
    assert h1["principals"] == ["role:viewer"]
    assert h1["condition"] == {"status": "open"}
    assert h1["masked_properties"] == ["ssn"]
    assert h1["certified"] is False


def test_apply_h1_policy_rejects_mismatch_and_bad_effect(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-h1-bad"
    with pytest.raises(ValueError, match="h1_resource_mismatch"):
        apply_h1_policy(domain, "e1", {"resource": "other", "effect": "allow", "principals": []})
    with pytest.raises(ValueError, match="h1_effect_invalid"):
        apply_h1_policy(domain, "e1", {"effect": "maybe", "principals": ["role:viewer"]})


def test_put_route_and_panel_wire_h1_policy():
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "action_routes.py"
    ).read_text(encoding="utf-8")
    assert "apply_graph_h1_policy" in routes
    assert "h1_policy" in routes
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "h1_policy" in panel
    assert "应用 H.1" in panel
    assert "非完整策略编辑器" in panel
