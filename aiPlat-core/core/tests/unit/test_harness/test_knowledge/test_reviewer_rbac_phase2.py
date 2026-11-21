"""N04/N12 deepen：Fact publish reviewer 角色门；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_reviewer_rbac_gate,
    run_reviewer_rbac_suite,
)
from core.harness.knowledge_pipeline.fact_state_machine import (
    assert_reviewer_role,
    evaluate_reviewer_rbac_gate as core_gate,
    FactStateMachineError,
    run_reviewer_rbac_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 4
    assert suite["certified"] is False
    assert suite["n04_full_conformance"] is False
    assert suite["n12_full_conformance"] is False
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["n12_full_conformance"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


@pytest.mark.asyncio
async def test_facade_suite():
    suite = await run_reviewer_rbac_suite()
    assert suite["ok"] is True
    gate = evaluate_reviewer_rbac_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_assert_reviewer_role_config(monkeypatch):
    monkeypatch.setenv("AIPLAT_FACT_REVIEWER_RBAC", "1")
    monkeypatch.setenv("AIPLAT_FACT_REVIEWER_ROLES", "reviewer,knowledge_admin")
    assert_reviewer_role(role="reviewer")
    with pytest.raises(FactStateMachineError, match="reviewer rbac denied"):
        assert_reviewer_role(role="viewer")
    monkeypatch.setenv("AIPLAT_FACT_REVIEWER_RBAC", "0")
    assert_reviewer_role(role="")  # opt-out


def test_docs_and_wiring_state():
    fsm = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "fact_state_machine.py"
    )
    text = fsm.read_text(encoding="utf-8")
    assert "assert_reviewer_role" in text
    assert "run_reviewer_rbac_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_reviewer_rbac_suite" in facade.read_text(encoding="utf-8")
    route = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "fact_state_routes.py"
    )
    assert "role=body.role" in route.read_text(encoding="utf-8")
