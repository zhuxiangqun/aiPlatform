"""Suite Profile exam — sample_manifest sole execution list."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_pack_legacy import ManifestValidationError
from core.apps.eval.service.capability_case_bank import (
    PROFILE_ID_SMOKE,
    build_agent_capability_cases,
)
from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile
from core.apps.eval.service.suite_profile_exam import (
    index_cases_by_id,
    run_suite_profile_exam,
    verify_capability_manifest_hashes,
)


@pytest.mark.asyncio
async def test_run_smoke_profile_dry_executes_manifest_only():
    out = await run_suite_profile_exam(profile_id=PROFILE_ID_SMOKE, live=False)
    assert out["ok"] is True
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
    assert out["manifest_case_count"] == 13  # v1.1: 1× per in-scope capability
    assert out["executed_case_count"] == 13
    assert out["counts"]["tasks"] == 13
    # dry stub should pass most lexical must_contain by construction
    assert out["counts"]["pass"] + out["counts"]["fail"] + out["counts"]["inconclusive"] + out[
        "counts"
    ]["error"] == 13
    plan = out.get("evaluation_plan") or {}
    assert plan.get("sample_manifest")
    assert len(out["cases"]) == 13


@pytest.mark.asyncio
async def test_run_rejects_empty_manifest():
    bank = build_agent_capability_cases()
    plan = compile_plan_from_suite_profile(profile_id=PROFILE_ID_SMOKE, cases=bank)
    plan["sample_manifest"] = []
    # Direct verify path
    with pytest.raises(ManifestValidationError):
        verify_capability_manifest_hashes([], index_cases_by_id(bank))


def test_verify_hash_mismatch_fail_closed():
    bank = build_agent_capability_cases()
    by_id = index_cases_by_id(bank)
    cid = next(iter(by_id))
    with pytest.raises(ManifestValidationError, match="hash mismatch"):
        verify_capability_manifest_hashes(
            [{"case_id": cid, "hash": "sha256:deadbeef"}],
            by_id,
        )


def test_verify_unknown_case_fail_closed():
    bank = build_agent_capability_cases()
    with pytest.raises(ManifestValidationError, match="not in case bank"):
        verify_capability_manifest_hashes(
            [{"case_id": "no.such.case", "hash": "sha256:x"}],
            index_cases_by_id(bank),
        )


@pytest.mark.asyncio
async def test_holdout_rows_skipped_not_executed():
    plan = compile_plan_from_suite_profile(profile_id="agent.benchmark.v1")
    # Inject a holdout flag onto first manifest row after compile via custom cases path:
    # run with benchmark; holdout_manifest cases should not appear as executed tasks
    out = await run_suite_profile_exam(profile_id="agent.benchmark.v1", live=False)
    assert out["ok"] is True
    hold_ids = {
        str(x.get("case_id") or "")
        for x in (out.get("evaluation_plan") or {}).get("holdout_manifest") or []
    }
    executed = {
        str(c.get("case_id") or "")
        for c in out["cases"]
        if c.get("status") != "skipped"
    }
    assert executed.isdisjoint(hold_ids)
    assert out["accuracy_claim"] is False
