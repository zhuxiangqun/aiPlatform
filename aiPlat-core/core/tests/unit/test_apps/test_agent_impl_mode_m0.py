"""M0: impl_modes resolve, selection≠execution, rank_fingerprint, contracts gate."""
from __future__ import annotations

from core.apps.eval.service.agent_impl_mode import (
    compute_rank_fingerprint,
    evaluate_m0_impl_mode_contracts,
    load_mode_core_matrix,
    plan_executions_per_mode,
    resolve_impl_modes,
    select_capabilities_union,
)


def test_resolve_unknown_not_default_react():
    out = resolve_impl_modes({})
    assert out["primary"] == "unknown"
    assert out["ok"] is False


def test_resolve_deferred_multi_agent():
    out = resolve_impl_modes({"agent_type": "multi_agent"})
    assert out["primary"] == "deferred"
    assert out["deferred_as"] == "multi_agent"


def test_resolve_explicit_primary_secondary():
    out = resolve_impl_modes(
        {
            "impl_modes": {
                "primary": "react",
                "secondary": ["conversational", "pipeline"],
                "confidence": "explicit",
                "source": "AGENT.md",
            }
        }
    )
    assert out["primary"] == "react"
    assert out["secondary"] == ["conversational"]
    assert out["deferred_secondary"] == ["pipeline"]
    assert out["ok"] is True


def test_selection_union_ne_execution_union():
    impl = resolve_impl_modes(
        {
            "impl_modes": {
                "primary": "react",
                "secondary": ["conversational"],
                "confidence": "explicit",
                "source": "config",
            }
        }
    )
    sel = select_capabilities_union(impl)
    exe = plan_executions_per_mode(impl)
    assert "tool_selection" in sel["selection_union"]
    assert "multi_turn_memory" in sel["selection_union"]
    assert sel["execution_policy"] == "per_mode_separate_runs"
    assert exe["merged_execution_forbidden"] is True
    modes = {r["impl_mode"] for r in exe["runs"]}
    assert "react" in modes and "conversational" in modes
    react_run = next(r for r in exe["runs"] if r["impl_mode"] == "react")
    conv_run = next(r for r in exe["runs"] if r["impl_mode"] == "conversational")
    assert "tool_selection" in react_run["capabilities"]
    assert "tool_selection" not in conv_run["capabilities"]
    assert "multi_turn_memory" in conv_run["capabilities"]


def test_rank_fingerprint_ignores_agent_id():
    common = dict(
        manifest_hash="sha256:m",
        prompt_hash="sha256:p",
        oracle_hash="sha256:o",
        runner_judge_version="j1",
        model_fingerprint="m1",
        runtime_tier="workspace_execute",
        runtime_parts_contract="rp1",
        tools_contract_hash="t=none",
        retrieval_contract_hash="r=none",
        session_contract_hash="s=none",
    )
    a = compute_rank_fingerprint(**common, agent_id="a1", workspace_id="w1")
    b = compute_rank_fingerprint(**common, agent_id="a2", workspace_id="w2")
    assert a["ok"] is True
    assert a["rank_fingerprint"] == b["rank_fingerprint"]
    assert "agent_id" in a["excluded_fields"]


def test_matrix_plan_execute_a6_subtypes():
    mat = load_mode_core_matrix()
    pe = mat["modes"]["plan_execute"]
    assert "tool_failure_recovery" in pe["a6_forbidden_subtypes"]
    assert set(pe["a6_allowed_subtypes"]) >= {"replan", "step_conflict", "text_recovery"}


def test_m0_contracts_gate_green():
    report = evaluate_m0_impl_mode_contracts()
    assert report["ok"] is True, report.get("errors") or report.get("checks")
    assert report["m1_blocked"] is False
    assert report["claim_eligible"] is False
    assert report["rank_claim"] is False
    assert all(report["m0_exit_checklist"].values())
