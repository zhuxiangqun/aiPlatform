"""N08 deepen：Policy/Approval/Audit + kill switch；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_action_policy_audit_gate,
    run_action_policy_audit_suite,
)
from core.harness.ontology_engine.action_registry import (
    action_kill_switch_active,
    evaluate_action_policy_audit_gate as core_gate,
    run_action_policy_audit_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["n08_full_conformance"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_n08_full_forbidden" in honesty["issues"]


@pytest.mark.asyncio
async def test_facade_suite():
    suite = await run_action_policy_audit_suite()
    assert suite["ok"] is True
    gate = evaluate_action_policy_audit_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_kill_switch_env(monkeypatch):
    monkeypatch.delenv("AIPLAT_ACTION_KILL_SWITCH", raising=False)
    assert action_kill_switch_active() is False
    monkeypatch.setenv("AIPLAT_ACTION_KILL_SWITCH", "1")
    assert action_kill_switch_active() is True


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "ontology_engine"
        / "action_registry.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "action_kill_switch_active" in text
    assert "run_action_policy_audit_suite" in text
    assert "require_approval 且无 threshold" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_action_policy_audit_suite" in facade.read_text(encoding="utf-8")
