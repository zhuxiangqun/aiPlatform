"""Subject Suite Profile exam uses matching Subject bank (claim closed)."""
from __future__ import annotations

import pytest

from core.apps.eval.service.suite_profile_exam import run_suite_profile_exam


@pytest.mark.asyncio
async def test_prompt_smoke_exam_uses_prompt_bank():
    out = await run_suite_profile_exam(
        profile_id="prompt.smoke.v1", live=False, max_cases=0
    )
    assert out["ok"] is True
    assert out["subject_kind"] == "prompt"
    assert out["object_type_member"] is True
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
    assert out["manifest_case_count"] == 3
    assert out["executed_case_count"] == 3
    ids = [str(c.get("case_id") or "") for c in out["cases"]]
    assert all(i.startswith("prompt.") for i in ids if i)


@pytest.mark.asyncio
async def test_api_smoke_exam_scripted_pass_path():
    out = await run_suite_profile_exam(profile_id="api.smoke.v1", live=False)
    assert out["ok"] is True
    assert out["subject_kind"] == "api"
    assert out["manifest_case_count"] == 3
    # scripted_answer should satisfy lexical must_contain for smoke fixtures
    assert out["counts"]["pass"] >= 1
    assert out["counts"]["error"] == 0


@pytest.mark.asyncio
async def test_kb_regression_exam_subject_local():
    out = await run_suite_profile_exam(
        profile_id="kb.regression.v1", live=False, max_cases=5
    )
    assert out["ok"] is True
    assert out["subject_kind"] == "kb"
    assert out["object_type_member"] is False
    assert out["executed_case_count"] == 5
    assert out["claim_eligible"] is False
    plan = out.get("evaluation_plan") or {}
    assert plan.get("subject_kind") == "kb"


@pytest.mark.asyncio
async def test_agent_smoke_still_works():
    out = await run_suite_profile_exam(profile_id="agent.smoke.v1", live=False)
    assert out["ok"] is True
    assert out["subject_kind"] == "agent"
    assert out["manifest_case_count"] == 13
