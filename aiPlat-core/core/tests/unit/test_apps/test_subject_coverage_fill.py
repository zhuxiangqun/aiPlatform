"""Subject-aware P3 coverage analyze / heatmap (claim closed)."""
from __future__ import annotations

from core.apps.eval.service.capability_coverage_fill import (
    analyze_capability_coverage,
    generate_coverage_fill_candidates,
    subject_capability_scope,
)
from core.apps.eval.service.suite_profile_report import build_capability_heatmap


def test_prompt_smoke_coverage_uses_prompt_scope():
    report = analyze_capability_coverage(profile_id="prompt.smoke.v1")
    assert report["ok"] is True
    assert report["subject_kind"] == "prompt"
    assert report["total_in_scope"] == 5
    assert report["claim_eligible"] is False
    assert "efficiency" not in report["in_scope"]
    # Prompt smoke quotas are met by the seed bank → no agent-cap phantom gaps.
    assert report["n_gaps"] == 0
    assert report["covered_capabilities"] == 5


def test_api_smoke_heatmap_subject_local():
    heat = build_capability_heatmap(profile_id="api.smoke.v1")
    assert heat["ok"] is True
    assert heat["subject_kind"] == "api"
    assert heat["claim_eligible"] is False
    assert len(heat["rows"]) == 3
    ids = {r["capability_id"] for r in heat["rows"]}
    assert ids == {"task_completion", "safety", "robustness"}
    assert heat["unknown_capabilities"] == []


def test_subject_scope_sets_differ_from_agent():
    agent_in, _agent_out = subject_capability_scope("agent")
    prompt_in, prompt_out = subject_capability_scope("prompt")
    assert len(agent_in) == 13
    assert len(prompt_in) == 5
    assert prompt_out == set()
    assert "efficiency" in agent_in
    assert "efficiency" not in prompt_in


def test_prompt_template_fill_tags_subject():
    out = generate_coverage_fill_candidates(
        profile_id="prompt.smoke.v1",
        min_per_capability=8,
        method="template",
        seed="9",
    )
    assert out["ok"] is True
    assert out["subject_kind"] == "prompt"
    assert out["n_candidates"] > 0
    assert out["claim_eligible"] is False
    for c in out["candidates"]:
        assert "prompt" in (c.get("tags") or [])
        assert (c.get("applies_to") or {}).get("object_types") == ["prompt"]


def test_agent_regression_still_zero_gap():
    report = analyze_capability_coverage(profile_id="agent.regression.v1")
    assert report["subject_kind"] == "agent"
    assert report["n_gaps"] == 0
    assert report["total_in_scope"] == 13
