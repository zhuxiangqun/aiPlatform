"""M1b mode-aware exam — rag column, retrieval required, tools/network none."""
from __future__ import annotations

import pytest

from core.apps.eval.service.mode_aware_exam import (
    ModeAwareExamError,
    enforce_m1b_environment,
    load_m1b_mode_cases,
    run_m1b_mode_exam,
)


def test_m1b_cases_load():
    cases = load_m1b_mode_cases("rag")
    assert len(cases) >= 4
    assert all(c.get("retrieval_fixture") for c in cases)
    assert all(not c.get("session_group") for c in cases)


def test_env_lock_retrieval_required():
    errs = enforce_m1b_environment("rag", {"tool_calls": [], "retrieval_used": False})
    assert "environment_violation:retrieval_required" in errs


def test_env_lock_tools_forbidden():
    errs = enforce_m1b_environment(
        "rag",
        {
            "tool_calls": [{"name": "search"}],
            "retrieval_used": True,
            "retrieval_hits": [{"id": "x"}],
        },
    )
    assert "environment_violation:tools" in errs


def test_env_lock_ok_with_hits():
    errs = enforce_m1b_environment(
        "rag",
        {
            "tool_calls": [],
            "retrieval_used": True,
            "retrieval_hits": [{"id": "doc-1", "content": "x"}],
            "network_used": False,
        },
    )
    assert errs == []


@pytest.mark.asyncio
async def test_run_m1b_scripted_rag_column():
    out = await run_m1b_mode_exam(live=False)
    assert out["ok"] is True, out
    assert out["phase"] == "m1b"
    assert out["claim_eligible"] is False
    assert out["rank_claim"] is False
    assert set(out["columns"]) == {"rag"}
    col = out["columns"]["rag"]
    assert col["separate_create_agent"] is True
    assert col["environment_lock"]["retrieval"] == "required"
    assert col["environment_lock"]["tools"] == "none"
    assert col["retrieval_backend"] == "fixture"
    assert col["n_passed"] == col["n_cases"] >= 4
    for row in col["results"]:
        assert row["execution_mode"] == "rag"
        assert row["runtime_tier"] == "fixture"
        assert row["n_retrieval_hits"] >= 1
        assert row["subject"]["impl_mode"] == "rag"


@pytest.mark.asyncio
async def test_run_m1b_rejects_non_m1b_mode():
    with pytest.raises(ModeAwareExamError, match="m1b_mode_not_allowed"):
        await run_m1b_mode_exam(live=False, modes=["react"])
