"""C4: stage outcome sample bank (queryable; no topology mutation)."""
from __future__ import annotations

from types import SimpleNamespace

from core.harness.execution.stage_handoff import apply_gate_failure, gate_check, write_stage_handoff
from core.harness.execution.stage_outcome_samples import (
    OUTCOME_FAILED,
    OUTCOME_GATE_HITL,
    OUTCOME_OK,
    query_stage_outcome_samples,
    record_stage_outcome_sample,
    summarize_stage_outcome_samples,
)


def test_record_and_query_stage_outcome_samples(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    stage = SimpleNamespace(
        id="architect_agent",
        skill_name="architecture_design",
        output_artifact="architecture",
    )
    state = {
        "project_id": "prj_c4",
        "run_id": "run_1",
        "architecture": {
            "components": [{"name": "api"}],
            "raw_output": "{}",
        },
    }
    row = record_stage_outcome_sample(
        outcome=OUTCOME_OK,
        stage=stage,
        state=state,
        artifact_key="architecture",
        source="unit",
    )
    assert row["outcome"] == OUTCOME_OK
    assert row["stage_id"] == "architect_agent"
    assert row["skill_name"] == "architecture_design"
    assert "components" in row["structured_keys"]

    record_stage_outcome_sample(
        outcome=OUTCOME_FAILED,
        stage=stage,
        state=state,
        error="short output",
        source="unit",
    )
    rows = query_stage_outcome_samples(limit=10, project_id="prj_c4")
    assert len(rows) >= 2
    fails = query_stage_outcome_samples(limit=10, outcome=OUTCOME_FAILED)
    assert all(r["outcome"] == OUTCOME_FAILED for r in fails)
    summary = summarize_stage_outcome_samples(rows)
    assert summary["total"] >= 2
    assert OUTCOME_OK in summary["by_outcome"]


def test_c4_wired_via_write_stage_handoff(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    stage = SimpleNamespace(
        id="pm_agent",
        skill_name="requirement_analysis",
        output_artifact="prd",
        order=0,
        handoff_required=False,
    )
    state = {
        "project_id": "prj_handoff",
        "prd": {"title": "x", "functional_requirements": [{"id": "FR-1"}]},
    }
    write_stage_handoff(
        state,
        stage=stage,
        artifact_key="prd",
        status="ok",
        stages=[stage],
    )
    rows = query_stage_outcome_samples(limit=5, project_id="prj_handoff")
    assert rows
    assert rows[-1]["outcome"] == OUTCOME_OK
    assert rows[-1]["source"] == "write_stage_handoff"


def test_c4_wired_via_apply_gate_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    stage = SimpleNamespace(
        id="arch",
        skill_name="architecture_design",
        output_artifact="architecture",
        output_schema={"type": "object", "required": ["components"]},
        gate_on_fail="hitl",
        handoff_required=False,
        input_artifacts=[],
        hitl_phase="review",
    )
    state = {"project_id": "prj_gate", "architecture": {"raw_output": "{}"}}
    r = gate_check(stage, state, phase="output")
    assert r["ok"] is False
    apply_gate_failure(state, stage, r)
    rows = query_stage_outcome_samples(limit=20, project_id="prj_gate")
    outcomes = {r["outcome"] for r in rows}
    assert OUTCOME_GATE_HITL in outcomes or OUTCOME_FAILED in outcomes
