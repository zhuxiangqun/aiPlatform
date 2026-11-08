"""P1 agent.capability Case Bank + regression profile."""
from __future__ import annotations

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PROFILE_ID,
    agent_regression_profile,
    build_agent_capability_cases,
    default_seed_dir,
    validate_agent_capability_bank,
    validate_capability_case,
)
from core.apps.eval.service.capability_id_map import V1_IN_SCOPE, V1_OUT_OF_SCOPE


def test_bank_size_and_all_valid():
    cases = build_agent_capability_cases()
    assert len(cases) == 64
    report = validate_agent_capability_bank(cases)
    assert report["ok"] is True
    assert report["invalid_count"] == 0
    assert report["claim_eligible"] is False
    assert report["pack_id"] == PACK_ID
    counts: dict = {}
    for c in cases:
        cap = c["capabilities"][0]
        counts[cap] = counts.get(cap, 0) + 1
    for cap in V1_IN_SCOPE:
        assert counts.get(cap, 0) >= 8, cap


def test_only_v1_in_scope_capabilities():
    for c in build_agent_capability_cases():
        caps = c["capabilities"]
        assert caps
        assert caps[0] in V1_IN_SCOPE
        assert caps[0] not in V1_OUT_OF_SCOPE
        assert validate_capability_case(c) == []


def test_regression_profile_quotas_match_bank_and_exclude_tools():
    profile = agent_regression_profile()
    assert profile["profile_id"] == PROFILE_ID
    assert profile["claim_eligible"] is False
    assert profile["schema"] == "eval.suite_profile.v1"
    cases = build_agent_capability_cases()
    counts: dict = {}
    for c in cases:
        cap = c["capabilities"][0]
        counts[cap] = counts.get(cap, 0) + 1
    for cap, n in profile["quotas"].items():
        assert cap in V1_IN_SCOPE
        assert counts.get(cap, 0) >= n
    for banned in (
        "tool_selection",
        "tool_args",
        "tool_result_use",
        "multi_turn_memory",
        "long_context",
    ):
        assert banned not in profile["quotas"]


def test_seed_dir_under_workspace_seeds():
    path = default_seed_dir()
    assert path.name == "agent_capability"
    assert "workspace_seeds" in path.parts
    assert (path / f"pack.{PACK_ID}.v0.1.0.json").is_file()
    assert (path / f"profile.{PROFILE_ID}.json").is_file()
