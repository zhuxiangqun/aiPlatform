"""test_governance_report_wired.py — verify the governance report is wired into production.

Covers:
- build_run_report is re-exported via CoreFacade
- the report aggregates trace + cost + hypotheses + root-cause chain
- the explanation is human-readable
"""
import pytest

from core.harness.execution.decision_trace import record_decision, clear_trace
from core.harness.execution.governance_report import build_run_report


@pytest.fixture
def clean_run():
    run_id = "governance_test_run"
    clear_trace(run_id)
    yield run_id
    clear_trace(run_id)


def test_build_run_report_reexported_by_facade():
    from core.api import core_facade
    assert hasattr(core_facade, "build_run_report")


def test_report_aggregates_all_sections(clean_run):
    run_id = clean_run
    record_decision(run_id, "pm", depends_on=[], confidence=0.9)
    record_decision(run_id, "arch", depends_on=["pm"], confidence=0.3)
    record_decision(run_id, "code", depends_on=["arch"], confidence=0.8)
    record_decision(run_id, "test", depends_on=["code"], confidence=0.7)

    report = build_run_report(run_id, cost_used_usd=0.5, cost_budget_usd=1.0,
                              failed_stage_ids=["test"])

    assert report["run_id"] == run_id
    assert len(report["decisions"]) == 4
    assert report["cost"]["cost_used_usd"] == 0.5
    assert report["cost"]["cost_budget_usd"] == 1.0
    assert report["cost"]["over_budget"] is False
    assert report["failure_analysis"]["max_error_stage"] == "arch"
    assert report["failure_analysis"]["hypotheses"]
    assert len(report["failure_analysis"]["root_cause_chain"]) == 4
    assert "arch" in report["explanation"]
    assert "0.5000" in report["explanation"]


def test_report_over_budget_flag(clean_run):
    run_id = clean_run
    record_decision(run_id, "test", depends_on=[], confidence=0.7)
    report = build_run_report(run_id, cost_used_usd=2.0, cost_budget_usd=1.0)
    assert report["cost"]["over_budget"] is True


def test_report_empty_run(clean_run):
    run_id = clean_run
    report = build_run_report(run_id)
    assert report["run_id"] == run_id
    assert report["decisions"] == []
    assert report["failure_analysis"]["max_error_stage"] is None
