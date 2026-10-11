"""E3: execution path card on decision_trace + stage state."""

from __future__ import annotations

from unittest.mock import MagicMock

import core.harness.execution.decision_trace as dt
from core.harness.execution.decision_trace import (
    build_execution_decision,
    clear_trace,
    get_trace,
    record_decision,
)
from core.harness.execution.pipeline_engine import PipelineEngine
from core.schemas_builder import PipelineStageConfig


def test_build_execution_decision_inferred_from_profile():
    d = build_execution_decision(
        architecture_profile="react_tools",
        execution_backend="agent",
        agent_type="react",
        capability_profile="autonomous",
        execution_type="prompt",
        path="agent",
        upgrade_policy="signals",
    )
    assert d["architecture_profile"] == "react_tools"
    assert d["execution_backend"] == "agent"
    assert d["path"] == "agent"
    assert d["inferred_from"] == "architecture_profile"


def test_build_execution_decision_schema_default():
    d = build_execution_decision(path="llm")
    assert d["execution_backend"] == "llm"
    assert d["inferred_from"] == "schema_default"


def test_record_decision_persists_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(dt, "_TRACE_DIR", str(tmp_path / "traces"))
    run_id = "e3-run-1"
    clear_trace(run_id)
    ex = build_execution_decision(
        architecture_profile="oneshot",
        execution_backend="llm",
        path="llm",
        execution_type="prompt",
    )
    record_decision(run_id, "stage_a", execution=ex, confidence=0.8)
    tr = get_trace(run_id)
    rec = tr["decisions"][f"{run_id}_stage_a"]
    assert rec["execution"]["path"] == "llm"
    assert rec["execution"]["architecture_profile"] == "oneshot"
    clear_trace(run_id)


def test_emit_execution_decision_on_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(dt, "_TRACE_DIR", str(tmp_path / "traces"))
    eng = PipelineEngine.__new__(PipelineEngine)
    eng._config = MagicMock()
    eng._config.stages = []
    stage = PipelineStageConfig(
        id="s1",
        agent_id="coder",
        architecture_profile="react_tools",
        execution_backend="agent",
        agent_type="react",
        upgrade_policy="signals",
    )
    state: dict = {"project_id": "proj-e3", "_capability_profile": "full"}
    clear_trace("proj-e3")
    eng._emit_execution_decision(
        stage, state, path="agent", execution_type="prompt", confidence=0.7
    )
    assert state["_execution_decision"]["path"] == "agent"
    assert state["_execution_decision"]["architecture_profile"] == "react_tools"
    tr = get_trace("proj-e3")
    assert tr["decisions"]["proj-e3_s1"]["execution"]["path"] == "agent"
    clear_trace("proj-e3")