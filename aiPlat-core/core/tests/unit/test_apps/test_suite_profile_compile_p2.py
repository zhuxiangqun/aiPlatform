"""P2 Suite Profile → Plan v2 sample_manifest + P1 promote bank."""
from __future__ import annotations

import pytest

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PACK_VERSION,
    PROFILE_ID,
    agent_regression_profile,
    promote_agent_capability_bank,
)
from core.apps.eval.service.suite_profile_compile import (
    SuiteProfileCompileError,
    compile_plan_from_suite_profile,
    select_cases_for_profile,
)
from core.apps.eval.service.capability_case_bank import build_agent_capability_cases


def test_select_cases_meets_exact_quotas():
    cases = build_agent_capability_cases()
    profile = agent_regression_profile()
    selected, meta = select_cases_for_profile(cases, profile)
    # v1.1 regression quotas sum (legacy + A3–A5/A8/A9 floors)
    assert meta["taken"] == 57
    assert meta["degraded"] is False
    assert len(selected) == 57
    for row in meta["quota_trace"]:
        assert row["taken"] == row["quota"]


def test_compile_plan_writes_sample_manifest_and_closes_claim():
    plan = compile_plan_from_suite_profile()
    assert plan["ok"] is True
    assert plan["schema"].endswith("v2") or "plan" in plan["schema"]
    assert plan["profile_id"] == PROFILE_ID
    assert plan["claim_eligible"] is False
    assert plan["accuracy_claim"] is False
    manifest = plan["sample_manifest"]
    assert len(manifest) == 57
    assert plan["manifest_hash"].startswith("sha256:")
    assert plan["plan_id"].startswith("plan-")
    ids = [m["case_id"] for m in manifest]
    assert len(ids) == len(set(ids))


def test_compile_fail_closed_on_shortfall():
    profile = agent_regression_profile()
    profile = dict(profile)
    profile["quotas"] = {"clarification": 99}
    with pytest.raises(SuiteProfileCompileError, match="insufficient"):
        select_cases_for_profile(build_agent_capability_cases(), profile)


def test_compile_rejects_claim_eligible_true():
    profile = dict(agent_regression_profile())
    profile["claim_eligible"] = True
    with pytest.raises(SuiteProfileCompileError, match="claim_eligible"):
        select_cases_for_profile(build_agent_capability_cases(), profile)


def test_promote_agent_capability_bank_freezes(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = promote_agent_capability_bank(
        workspace_id="ws-cap",
        reviewer="owner",
        frozen_by="owner",
        notes="unit promote",
    )
    assert out["ok"] is True
    assert out["pack_id"] == PACK_ID
    assert out["version"] == PACK_VERSION
    assert out["kind"] == "frozen"
    assert out["status"] == "active"
    assert out["n_cases"] >= 64
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False

    again = promote_agent_capability_bank(workspace_id="ws-cap", reviewer="owner")
    assert again.get("noop") is True or again["kind"] == "frozen"
