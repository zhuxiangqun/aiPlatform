"""M1c mode-aware exam — react + fixture_mock sandbox; A3–A5 unknown."""
from __future__ import annotations

import os

import pytest

from core.apps.eval.service.mode_aware_exam import (
    ModeAwareExamError,
    enforce_m1c_environment,
    load_m1c_mode_cases,
    probe_m1c_sandbox,
    run_m1c_mode_exam,
)


def test_m1c_cases_load():
    cases = load_m1c_mode_cases("react")
    assert len(cases) >= 5
    assert any("tool_selection" in (c.get("capabilities") or []) for c in cases)


def test_probe_fixture_sandbox_ready():
    from core.apps.eval.service.mode_aware_exam import probe_linux_microvm_host

    probe = probe_m1c_sandbox()
    assert probe["fixture_sandbox_ready"] is True
    assert probe["sandbox_backend"] == "fixture_mock"
    assert probe["microvm_covered"] is False
    assert probe["capability_coverage_a3_a5"] == "unknown"
    linux = probe.get("linux_microvm") or {}
    assert linux.get("microvm_covered") is False
    assert linux.get("process_split_authorized") is False
    host = probe_linux_microvm_host()
    assert host["microvm_covered"] is False
    assert host["process_split_authorized"] is False
    # Darwin CI: non_linux → admit_ready false
    if host.get("os") != "linux":
        assert host["admit_ready"] is False


def test_env_lock_tools_required():
    errs = enforce_m1c_environment(
        "react",
        {"tool_calls": [], "sandbox_backend": "fixture_mock"},
    )
    assert "environment_violation:tools_required" in errs


def test_env_lock_sandbox_required():
    errs = enforce_m1c_environment(
        "react",
        {"tool_calls": [{"name": "echo"}], "sandbox_backend": "none"},
    )
    assert "environment_violation:sandbox_required" in errs


def test_env_lock_ok():
    errs = enforce_m1c_environment(
        "react",
        {
            "tool_calls": [{"name": "echo"}],
            "sandbox_backend": "fixture_mock",
            "retrieval_used": False,
            "network_used": False,
        },
    )
    assert errs == []


@pytest.mark.asyncio
async def test_run_m1c_scripted_react_column():
    out = await run_m1c_mode_exam(live=False)
    assert out["ok"] is True, out
    assert out["phase"] == "m1c"
    assert out["claim_eligible"] is False
    assert out["rank_claim"] is False
    assert out["capability_coverage"]["tool_selection"] == "unknown"
    assert set(out["columns"]) == {"react"}
    col = out["columns"]["react"]
    assert col["environment_lock"]["tools"] == "required"
    assert col["environment_lock"]["sandbox"] == "required"
    assert col["tool_backend"] == "mock"
    assert col["n_passed"] == col["n_cases"] >= 5
    for row in col["results"]:
        assert row["execution_mode"] == "react"
        assert row["runtime_tier"] == "fixture"
        assert row["capability_coverage"]["tool_selection"] == "unknown"


@pytest.mark.asyncio
async def test_run_m1c_live_blocked_without_env(monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_M1C_SANDBOX", raising=False)
    out = await run_m1c_mode_exam(live=True)
    assert out["ok"] is False
    assert "sandbox_not_ready" in (out.get("errors") or [])


@pytest.mark.asyncio
async def test_run_m1c_live_opt_in_fixture(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_M1C_SANDBOX", "1")
    out = await run_m1c_mode_exam(live=True)
    assert out["ok"] is True, out
    assert out["sandbox"]["live_sandbox_ready"] is True
    assert out["sandbox"]["microvm_covered"] is False
    for row in out["columns"]["react"]["results"]:
        assert row["runtime_tier"] == "workspace_execute"
        assert row["capability_coverage"]["tool_args"] == "unknown"


@pytest.mark.asyncio
async def test_run_m1c_rejects_non_m1c_mode():
    with pytest.raises(ModeAwareExamError, match="m1c_mode_not_allowed"):
        await run_m1c_mode_exam(live=False, modes=["rag"])
