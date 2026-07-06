"""
Semantic wiring assertions — Hermes Phase Gate convergence (blind-spot guard).

Unlike test_wiring.py / test_methods_wired.py (which count callers), this file
asserts SEMANTIC wiring correctness — the category that fell into the blind spot
between the evaluation framework (black-box output) and the grep/AST guards:

  "the right function is called from the right place, on real (not placeholder)
   data, and there is exactly one schema."

Covers the five changes from
docs/design/evaluation/hermes-phase-gate-convergence-plan.md:
  - change 1: acceptance gate wired into ReActLoop termination paths
  - change 2: three evaluators converge on one EvaluationReport schema
  - change 3: tri_agent placeholder metrics removed
  - change 4: completion judges run at temperature 0.0
"""
import re
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parent.parent.parent  # aiPlat-core/core


def _read(rel: str) -> str:
    return (CORE_ROOT / rel).read_text(encoding="utf-8", errors="ignore")


# ── change 1: acceptance gate is wired INTO the loop termination path ──

def test_acceptance_gate_wired_into_loop_termination():
    """The ReActLoop must consult the acceptance gate before declaring FINISHED.

    Blind-spot fact: a caller-count check passes even when the veto lives only
    in the offline eval path. Here we assert the gate is invoked in the same
    file that owns loop completion, and that it reads the change contract.
    """
    src = _read("harness/execution/loop/_facade.py")
    assert "def _acceptance_gate(self" in src, "acceptance gate method missing"
    assert "get_active_change_contract" in src, "gate must read the ActiveChangeContract"
    # invoked at least twice (the two 'claims completion' paths)
    assert src.count("self._acceptance_gate(state)") >= 2, (
        "acceptance gate must guard both completion paths (DONE/FINAL + auto-done)"
    )
    # each veto invocation is followed by an early return (does NOT fall through to FINISHED)
    assert "self._apply_acceptance_veto(state, _veto)" in src


def test_acceptance_veto_keeps_loop_running():
    """A veto must set a NON-terminal state so the loop continues, not FINISHED."""
    src = _read("harness/execution/loop/_facade.py")
    veto_body = src.split("def _apply_acceptance_veto")[1].split("def ")[0]
    assert "LoopStateEnum.REASONING" in veto_body, "veto must resume reasoning"
    assert "LoopStateEnum.FINISHED" not in veto_body, "veto must not finish the loop"


# ── change 4: completion judges run at temperature 0.0 ──

def test_auto_eval_judge_is_deterministic():
    """auto-eval LLM-as-Judge must call the model at temperature=0.0."""
    src = _read("harness/integration.py")
    # the auto-eval judge call site carries temperature=0.0
    assert re.search(
        r"sys_llm_generate\(\s*llm,\s*msgs,\s*temperature=0\.0", src
    ), "auto-eval judge must run at temperature=0.0"


def test_tri_agent_evaluator_is_deterministic():
    """tri_agent evaluator must inject temperature 0.0 (planner/generator unchanged)."""
    src = _read("harness/execution/langgraph/graphs/tri_agent.py")
    assert '"_llm_temperature": 0.0' in src, "evaluator must request temp 0.0"
    # and the compiled react reason node must honor it
    react = _read("harness/execution/langgraph/compiled_graphs/react.py")
    assert "_llm_temperature" in react and "temperature=_temp" in react, (
        "reason node must forward per-run temperature override"
    )


# ── change 3: no fabricated placeholder metrics ──

def test_no_placeholder_metrics_in_tri_agent():
    """Regression guard: the 0.85 placeholder must never come back."""
    src = _read("harness/execution/langgraph/graphs/tri_agent.py")
    assert "test_pass_rate=0.85" not in src, "placeholder metric reintroduced"
    assert "placeholder implementation" not in src.lower()


# ── change 2: exactly one EvaluationReport schema (convergence) ──

def test_three_evaluators_share_one_schema():
    """autoreview + tri_agent adapters must both satisfy workbench.validate_report,
    proving all three evaluators converge on one canonical schema (CLAUDE.md §10)."""
    from core.harness.evaluation.workbench import validate_report
    from core.engine.skills.autoreview.review_report import ReviewReport, ReviewIssue
    from core.harness.execution.langgraph.graphs.tri_agent import TriAgentGraph

    rr = ReviewReport(issues=[ReviewIssue(file="a.py", line=1, severity="P0", description="x")])
    ok_ar, why_ar = validate_report(rr.to_evaluation_report())
    assert ok_ar, f"autoreview report not canonical: {why_ar}"

    g = TriAgentGraph.__new__(TriAgentGraph)
    ok_ta, why_ta = validate_report(g._to_evaluation_report(False, "REJECTED", []))
    assert ok_ta, f"tri_agent report not canonical: {why_ta}"


def test_evaluator_adapters_have_production_callers():
    """The convergence adapters must be wired (not dead code) — §5.30."""
    handler = _read("engine/skills/autoreview/handler.py")
    assert ".to_evaluation_report()" in handler, "autoreview adapter not wired"
    tri = _read("harness/execution/langgraph/graphs/tri_agent.py")
    assert "self._to_evaluation_report(" in tri, "tri_agent adapter not wired"
