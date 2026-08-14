"""test_hypothesis_generator_wired.py — verify the hypothesis generator is wired into production.

Covers:
- generate_hypotheses is re-exported via CoreFacade
- hypothesis generation derives root-cause hypotheses from the decision trace
- hypotheses reference the max error-contribution node
"""
import pytest

from core.harness.execution.decision_trace import record_decision, clear_trace
from core.harness.execution.hypothesis_generator import generate_hypotheses


@pytest.fixture
def clean_run():
    run_id = "hypothesis_test_run"
    clear_trace(run_id)
    yield run_id
    clear_trace(run_id)


def test_generate_hypotheses_reexported_by_facade():
    from core.api import core_facade
    assert hasattr(core_facade, "generate_hypotheses")


def test_hypotheses_localize_low_confidence_stage(clean_run):
    run_id = clean_run
    record_decision(run_id, "prd", depends_on=[], confidence=0.9)
    record_decision(run_id, "arch", depends_on=["prd"], confidence=0.3)
    record_decision(run_id, "code", depends_on=["arch"], confidence=0.8)
    record_decision(run_id, "test", depends_on=["code"], confidence=0.7)

    hypotheses = generate_hypotheses(run_id, failed_stage_ids=["test"])

    assert len(hypotheses) >= 1
    top = hypotheses[0]
    assert top["stage_id"] == "arch", top
    assert "arch" in top["hypothesis"]
    assert "suggested_action" in top
    assert "regenerate" in top["suggested_action"]
    assert top["confidence"] > 0


def test_hypotheses_ranked_by_contribution(clean_run):
    run_id = clean_run
    record_decision(run_id, "prd", depends_on=[], confidence=0.95)
    record_decision(run_id, "arch", depends_on=["prd"], confidence=0.3)
    record_decision(run_id, "schema", depends_on=["prd"], confidence=0.9)
    record_decision(run_id, "code", depends_on=["arch", "schema"], confidence=0.8)
    record_decision(run_id, "test", depends_on=["code"], confidence=0.7)

    hypotheses = generate_hypotheses(run_id, failed_stage_ids=["test"])

    assert hypotheses[0]["stage_id"] == "arch"
    # sorted descending by confidence
    confidences = [h["confidence"] for h in hypotheses]
    assert confidences == sorted(confidences, reverse=True)


def test_hypotheses_empty_when_no_upstream(clean_run):
    run_id = clean_run
    record_decision(run_id, "test", depends_on=[], confidence=0.7)
    hypotheses = generate_hypotheses(run_id, failed_stage_ids=["test"], test_report="x")
    # no upstream → fallback hypothesis with stage_id None
    assert hypotheses[0]["stage_id"] is None
