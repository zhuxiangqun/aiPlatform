"""test_decision_trace_wired.py — verify decision_trace is wired into production.

Covers:
- record_decision has a production caller (pipeline_engine._run_stage_skill)
- locate_max_error_node is re-exported via CoreFacade (platform caller)
- the error-localization algorithm attributes contribution correctly
"""
import os
import pytest

from core.harness.execution.decision_trace import (
    record_decision,
    locate_max_error_node,
    trace_root_cause_chain,
    build_fix_plan,
    get_trace,
    clear_trace,
)


@pytest.fixture
def clean_run():
    run_id = "wiring_test_run"
    clear_trace(run_id)
    yield run_id
    clear_trace(run_id)


def test_record_decision_has_production_caller():
    """record_decision is imported by pipeline_engine.py (non-test caller)."""
    engine = os.path.join(os.path.dirname(__file__), "..", "..",
                          "core", "harness", "execution", "pipeline_engine.py")
    engine = os.path.abspath(engine)
    assert os.path.isfile(engine), f"pipeline_engine.py not found at {engine}"
    with open(engine, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "decision_trace" in src and "record_decision" in src


def test_locate_max_error_node_reexported_by_facade():
    """locate_max_error_node is re-exported by CoreFacade."""
    from core.api import core_facade
    assert hasattr(core_facade, "locate_max_error_node")
    assert hasattr(core_facade, "record_decision")


def test_locate_max_error_node_returns_max_contribution(clean_run):
    """Backward walk attributes error to the lowest-confidence upstream node."""
    run_id = clean_run
    # Chain: prd -> arch -> code -> test
    record_decision(run_id, "prd", depends_on=[], confidence=0.9)
    record_decision(run_id, "arch", depends_on=["prd"], confidence=0.3)
    record_decision(run_id, "code", depends_on=["arch"], confidence=0.8)
    record_decision(run_id, "test", depends_on=["code"], confidence=0.7)

    result = locate_max_error_node(run_id, failed_stage_ids=["test"])

    # The failing node is "test"; walking back, "code" (conf 0.8) and "arch"
    # (conf 0.3) are candidates. arch has the largest (1 - confidence).
    assert result["stage_id"] == "arch", result
    assert result["error_contribution"] > 0
    # (1 failed / 1 downstream) * (1 - 0.3) = 0.7
    assert abs(result["error_contribution"] - 0.7) < 1e-6


def test_locate_max_error_node_no_upstream_returns_none(clean_run):
    run_id = clean_run
    record_decision(run_id, "test", depends_on=[], confidence=0.7)
    result = locate_max_error_node(run_id, failed_stage_ids=["test"])
    # test has no upstream, so no ancestor candidate explains the failure.
    assert result["stage_id"] is None
    assert result["error_contribution"] == 0.0


def test_get_trace_roundtrip(clean_run):
    run_id = clean_run
    record_decision(run_id, "prd", depends_on=[], confidence=0.9)
    trace = get_trace(run_id)
    assert f"{run_id}_prd" in trace["decisions"]
    assert trace["decisions"][f"{run_id}_prd"]["confidence"] == 0.9


def test_depends_on_normalized_to_decision_ids(clean_run):
    """record_decision normalizes stage_ids to decision_ids for graph edges."""
    run_id = clean_run
    record_decision(run_id, "prd", depends_on=[], confidence=0.9)
    record_decision(run_id, "arch", depends_on=["prd"], confidence=0.7)
    trace = get_trace(run_id)
    arch = trace["decisions"][f"{run_id}_arch"]
    assert arch["depends_on"] == [f"{run_id}_prd"]


def test_branching_graph_localizes_lowest_confidence_upstream(clean_run):
    """A branching dependency graph attributes failure to the weakest upstream.

    prd(0.9) ── arch(0.3) ──┐
                             ├── code(0.8) ── test(0.7)  ← fails
    prd(0.9) ── schema(0.9) ─┘
    """
    run_id = clean_run
    record_decision(run_id, "prd", depends_on=[], confidence=0.9)
    record_decision(run_id, "arch", depends_on=["prd"], confidence=0.3)
    record_decision(run_id, "schema", depends_on=["prd"], confidence=0.9)
    record_decision(run_id, "code", depends_on=["arch", "schema"], confidence=0.8)
    record_decision(run_id, "test", depends_on=["code"], confidence=0.7)

    result = locate_max_error_node(run_id, failed_stage_ids=["test"])

    assert result["stage_id"] == "arch", result
    assert result["failed_downstream"] == 1
    assert result["total_downstream"] == 1
    assert abs(result["error_contribution"] - 0.7) < 1e-6


def test_branching_graph_common_ancestor_not_blamed(clean_run):
    """A high-confidence common ancestor is not blamed over a weak branch."""
    run_id = clean_run
    record_decision(run_id, "prd", depends_on=[], confidence=0.95)
    record_decision(run_id, "arch", depends_on=["prd"], confidence=0.3)
    record_decision(run_id, "schema", depends_on=["prd"], confidence=0.9)
    record_decision(run_id, "code", depends_on=["arch", "schema"], confidence=0.8)
    record_decision(run_id, "test", depends_on=["code"], confidence=0.7)

    result = locate_max_error_node(run_id, failed_stage_ids=["test"])
    assert result["stage_id"] == "arch", result


def test_trace_root_cause_chain_orders_deepest_root_first(clean_run):
    """The vertical chain is ordered root-first with correct depth."""
    run_id = clean_run
    record_decision(run_id, "pm", depends_on=[], confidence=0.92)
    record_decision(run_id, "arch", depends_on=["pm"], confidence=0.3)
    record_decision(run_id, "code", depends_on=["arch"], confidence=0.85)
    record_decision(run_id, "test", depends_on=["code"], confidence=0.8)

    chain = trace_root_cause_chain(run_id, failed_stage_ids=["test"])

    assert [c["stage_id"] for c in chain] == ["pm", "arch", "code", "test"]
    assert chain[0]["depth"] == 3  # pm is deepest root
    assert chain[-1]["depth"] == 0  # test is the failure node


def test_trace_root_cause_chain_reexported_by_facade():
    from core.api import core_facade
    assert hasattr(core_facade, "trace_root_cause_chain")


def test_locate_max_error_node_resolves_by_agent_id(clean_run):
    """Failure localization matches failed stages by agent_id, not just stage_id."""
    run_id = clean_run
    record_decision(run_id, "canvas_node_1", depends_on=[], confidence=0.9, agent_id="pm_agent")
    record_decision(run_id, "canvas_node_2", depends_on=["canvas_node_1"], confidence=0.3, agent_id="architect_agent")
    record_decision(run_id, "canvas_node_3", depends_on=["canvas_node_2"], confidence=0.8, agent_id="agent_engineer")

    # failed_stage_ids use agent_id (what the fix flow knows), not stage_id
    result = locate_max_error_node(run_id, failed_stage_ids=["agent_engineer"])

    assert result["stage_id"] == "canvas_node_2", result  # architect is the low-conf culprit
    assert abs(result["error_contribution"] - 0.7) < 1e-6


def test_build_fix_plan_single_root_cause(clean_run):
    """A low-confidence upstream node yields a single-stage plan."""
    run_id = clean_run
    record_decision(run_id, "n1", depends_on=[], confidence=0.9, agent_id="pm")
    record_decision(run_id, "n2", depends_on=["n1"], confidence=0.25, agent_id="arch")  # low conf root cause
    record_decision(run_id, "n3", depends_on=["n2"], confidence=0.85, agent_id="code")
    record_decision(run_id, "n4", depends_on=["n2"], confidence=0.85, agent_id="frontend")

    plan = build_fix_plan(run_id, failed_stage_ids=["code", "frontend"])
    assert plan == ["arch"], plan


def test_build_fix_plan_falls_back_to_earliest_failed_stage(clean_run):
    """Independent bugs with no low-conf root cause → earliest failed stage."""
    run_id = clean_run
    record_decision(run_id, "n1", depends_on=[], confidence=0.9, agent_id="pm")
    record_decision(run_id, "n2", depends_on=["n1"], confidence=0.85, agent_id="backend")
    record_decision(run_id, "n3", depends_on=["n2"], confidence=0.85, agent_id="frontend")

    plan = build_fix_plan(run_id, failed_stage_ids=["backend", "frontend"])
    assert plan == ["backend"], plan  # upstream-most failed stage


def test_build_fix_plan_empty_trace_returns_first_failed(clean_run):
    """Empty trace → return the first failed stage (per-stage fallback)."""
    run_id = clean_run
    plan = build_fix_plan(run_id, failed_stage_ids=["backend", "frontend"])
    assert plan == ["backend"], plan


def test_build_fix_plan_single_failed_returns_it(clean_run):
    run_id = clean_run
    plan = build_fix_plan(run_id, failed_stage_ids=["backend"])
    assert plan == ["backend"], plan


def test_build_fix_plan_reexported_by_facade():
    from core.api import core_facade
    assert hasattr(core_facade, "build_fix_plan")
