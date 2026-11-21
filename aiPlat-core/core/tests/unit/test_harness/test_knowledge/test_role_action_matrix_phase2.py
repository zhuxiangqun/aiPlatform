"""N07/N22 deepen：ABox 角色×动作轴；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_role_action_matrix_gate,
    run_role_action_matrix_suite,
)
from core.policy.graph_abox_acl import (
    evaluate_role_action_matrix_gate as core_gate,
    role_action_allowed,
    run_role_action_matrix_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 8
    assert suite["certified"] is False
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["deploy_rbac_source"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_deploy_rbac_forbidden" in honesty["issues"]


def test_facade_suite():
    suite = run_role_action_matrix_suite()
    assert suite["ok"] is True
    gate = evaluate_role_action_matrix_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_custom_role_env(monkeypatch):
    monkeypatch.setenv(
        "AIPLAT_ABOX_ROLE_ACTION_MATRIX",
        '{"sre": ["read", "update"], "viewer": ["read"]}',
    )
    assert role_action_allowed(role="sre", action="update")
    assert not role_action_allowed(role="sre", action="delete")
    assert not role_action_allowed(role="ghost", action="read")


def test_docs_and_wiring_state():
    mod = ROOT / "aiPlat-core" / "core" / "policy" / "graph_abox_acl.py"
    text = mod.read_text(encoding="utf-8")
    assert "load_role_action_matrix" in text
    assert "run_role_action_matrix_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_role_action_matrix_suite" in facade.read_text(encoding="utf-8")
