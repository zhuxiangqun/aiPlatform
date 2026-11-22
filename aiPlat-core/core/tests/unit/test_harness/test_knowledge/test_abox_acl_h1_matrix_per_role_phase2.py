"""N07/N22 deepen：H.1 role_actions per-role 矩阵；固定轴 / 非 certified / 非任意 RBAC。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.policy.graph_abox_acl import apply_h1_policy, check_entity_acl, entity_acl_to_h1


ROOT = Path(__file__).resolve().parents[6]


def test_apply_h1_role_actions_per_role(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    # 为什么：本用例验实例 deny 的 per-role 动作集；关掉全局角色×动作轴以免 viewer 无 update 能力干扰
    monkeypatch.setenv("AIPLAT_ABOX_ROLE_ACTION_MATRIX_ENABLED", "0")
    domain = "lock-service-acl-h1-per-role"
    eid = "Ticket-per-role"
    apply_h1_policy(
        domain,
        eid,
        {
            "resource": eid,
            "effect": "deny",
            "principals": ["role:viewer", "role:analyst"],
            "actions": ["read"],  # 并集兜底；实际以 role_actions 为准
            "role_actions": {
                "viewer": ["read"],
                "analyst": ["read", "update"],
            },
            "condition": {},
            "masked_properties": [],
        },
    )
    assert check_entity_acl(domain, eid, "viewer", "read") is False
    assert check_entity_acl(domain, eid, "viewer", "update") is True
    assert check_entity_acl(domain, eid, "analyst", "update") is False
    h1 = entity_acl_to_h1(domain, eid)
    assert h1["role_actions"]["viewer"] == ["read"]
    assert h1["role_actions"]["analyst"] == ["read", "update"]
    assert set(h1["actions"]) == {"read", "update"}
    assert h1["certified"] is False


def test_apply_h1_role_actions_rejects_bad(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-h1-per-role-bad"
    with pytest.raises(ValueError, match="h1_role_actions_values_must_be_list"):
        apply_h1_policy(
            domain,
            "e1",
            {
                "effect": "deny",
                "principals": ["role:viewer"],
                "actions": ["read"],
                "role_actions": {"viewer": "read"},
            },
        )
    with pytest.raises(ValueError, match="h1_role_actions_empty"):
        apply_h1_policy(
            domain,
            "e1",
            {
                "effect": "deny",
                "principals": ["role:viewer"],
                "actions": ["read"],
                "role_actions": {"viewer": []},
            },
        )


def test_panel_documents_h1_matrix_per_role():
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
    assert "role_actions" in text
    assert "per-role 矩阵" in text
    assert "h1RoleActions" in text
    assert "非 certified" in text
