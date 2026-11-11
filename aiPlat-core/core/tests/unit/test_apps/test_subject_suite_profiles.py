"""Subject Suite Profile discovery + compile (ADR P2; claim closed)."""
from __future__ import annotations

from core.apps.eval.service.capability_case_bank import (
    get_suite_profile,
    list_suite_profiles,
)
from core.apps.eval.service.subject_suite_profiles import (
    SUBJECT_SUITE_SCHEMA,
    get_subject_suite_profile,
    list_subject_suite_profiles,
    subject_suite_profile_inventory,
)
from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile


def test_list_subject_suite_profiles_covers_object_types():
    rows = list_subject_suite_profiles(include_agent=True)
    ids = {r["profile_id"] for r in rows}
    assert "agent.regression.v1" in ids
    assert "prompt.regression.v1" in ids
    assert "dataset.smoke.v1" in ids
    assert "system.regression.v1" in ids
    assert "tool.regression.v1" in ids
    assert all(r.get("claim_eligible") is False for r in rows)


def test_normalize_smoke_capability_quota_to_quotas():
    p = get_subject_suite_profile("api.smoke.v1")
    assert isinstance(p.get("quotas"), dict)
    assert p["quotas"]["task_completion"] == 1
    assert p["subject_kind"] == "api"


def test_compile_prompt_regression_plan():
    plan = compile_plan_from_suite_profile(profile_id="prompt.regression.v1")
    assert plan["ok"] is True
    assert plan["subject_kind"] == "prompt"
    assert plan["object_type_member"] is True
    assert len(plan["sample_manifest"]) == 25
    assert plan["claim_eligible"] is False
    assert plan["accuracy_claim"] is False
    assert plan["target_contract"]["object_type"] == "prompt"


def test_compile_subject_local_kb_plan():
    plan = compile_plan_from_suite_profile(profile_id="kb.regression.v1")
    assert plan["ok"] is True
    assert plan["subject_kind"] == "kb"
    assert plan["object_type_member"] is False
    assert len(plan["sample_manifest"]) == 15
    assert plan["claim_eligible"] is False
    tc = plan["target_contract"]
    assert tc.get("subject_kind") == "kb" or tc.get("object_type_registered") is False


def test_list_suite_profiles_delegates():
    assert len(list_suite_profiles()) == len(list_subject_suite_profiles())
    assert get_suite_profile("workflow.smoke.v1")["subject_kind"] == "workflow"


def test_subject_suite_profile_inventory_and_facade():
    inv = subject_suite_profile_inventory()
    assert inv["schema"] == SUBJECT_SUITE_SCHEMA
    assert inv["ok"] is True
    assert inv["profile_count"] >= 20
    assert inv["claim_eligible"] is False
    from core.api.core_facade import eval_subject_suite_profile_inventory

    assert eval_subject_suite_profile_inventory()["profile_count"] == inv["profile_count"]
