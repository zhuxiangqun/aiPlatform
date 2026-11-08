"""M1a mode-aware exam — plan_execute / conversational, env lock, separate columns."""
from __future__ import annotations

import pytest

from core.apps.eval.service.mode_aware_exam import (
    ModeAwareExamError,
    enforce_m1a_environment,
    load_m1a_mode_cases,
    run_m1a_mode_exam,
)


def test_m1a_cases_load():
    pe = load_m1a_mode_cases("plan_execute")
    cv = load_m1a_mode_cases("conversational")
    assert len(pe) >= 3
    assert len(cv) >= 3
    assert all(not c.get("session_group") for c in pe)


def test_env_lock_tools_violation():
    errs = enforce_m1a_environment(
        "plan_execute", {"tool_calls": [{"name": "echo"}]}
    )
    assert "environment_violation:tools" in errs


def test_env_lock_session_forbidden_on_plan_execute():
    errs = enforce_m1a_environment(
        "plan_execute", {"session_group": "g1", "tool_calls": []}
    )
    assert "environment_violation:session" in errs


def test_env_lock_session_allowed_on_conversational():
    errs = enforce_m1a_environment(
        "conversational",
        {"session_group": "g1", "tool_calls": [], "retrieval_used": False},
    )
    assert errs == []


@pytest.mark.asyncio
async def test_run_m1a_scripted_separate_columns():
    out = await run_m1a_mode_exam(live=False)
    assert out["ok"] is True, out
    assert out["claim_eligible"] is False
    assert out["rank_claim"] is False
    assert out["merged_execution_forbidden"] is True
    assert set(out["columns"]) == {"plan_execute", "conversational"}
    for mode, col in out["columns"].items():
        assert col["separate_create_agent"] is True
        assert col["n_cases"] >= 3
        assert col["n_passed"] == col["n_cases"]
        assert col["environment_lock"]["tools"] == "none"
        assert col["environment_lock"]["retrieval"] == "none"
        assert col["environment_lock"]["network"] == "none"
        for row in col["results"]:
            assert row["execution_mode"] == mode
            assert row["runtime_tier"] == "fixture"
            assert row["subject"]["impl_mode"] == mode


@pytest.mark.asyncio
async def test_run_m1a_rejects_non_m1a_mode():
    with pytest.raises(ModeAwareExamError, match="m1a_mode_not_allowed"):
        await run_m1a_mode_exam(live=False, modes=["react"])
