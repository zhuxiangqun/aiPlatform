"""Pre-deploy done_verify for llm + uses_file_output skill path."""

from __future__ import annotations

from core.harness.execution.done_verify import gate_llm_file_output_stage
from core.schemas_builder import PipelineStageConfig


def test_agent_backend_skips_gate():
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        execution_backend="agent",
        output_artifact="code",
    )
    state = {"code": {"raw_output": "DONE"}}
    assert (
        gate_llm_file_output_stage(
            stage=stage,
            state=state,
            result="DONE",
            artifact_key="code",
            backend="agent",
        )
        is None
    )


def test_non_file_output_skips_gate():
    stage = PipelineStageConfig(
        id="pm",
        agent_id="pm_agent",
        uses_file_output=False,
        execution_backend="llm",
        output_artifact="prd",
    )
    assert (
        gate_llm_file_output_stage(
            stage=stage,
            state={},
            result="short",
            artifact_key="prd",
            backend="llm",
        )
        is None
    )


def test_llm_file_output_vetoes_trivial_done():
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        execution_backend="llm",
        output_artifact="code",
        done_verify={
            "enabled": True,
            "min_output_length": 20,
            "reject_trivial_done": True,
            "require_testability": False,
            "review_gate": "quick",
        },
    )
    state = {"code": {"raw_output": "DONE"}}
    veto = gate_llm_file_output_stage(
        stage=stage,
        state=state,
        result="DONE",
        artifact_key="code",
        backend="llm",
    )
    assert veto and "trivial" in veto
    assert state.get("_done_verify_last_reason") == veto
    assert state["code"].get("status") == "failed"
    # review_gate must not false-veto llm oneshot (no follow-up skill loop)
    assert "review_gate" not in (veto or "")


def test_llm_file_output_passes_substantial_blob():
    body = (
        "## FILE: skills/demo/handler.py\n"
        "async def execute(params):\n"
        "    return {'ok': True}\n\n"
        "## FILE: skills/demo/test_handler.py\n"
        "def test_ok():\n"
        "    assert 1 + 1 == 2\n"
    )
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        execution_backend="llm",
        output_artifact="code",
        done_verify={
            "enabled": True,
            "min_output_length": 20,
            "reject_trivial_done": True,
            "require_testability": True,
            "testability_mode": "warn",
            "review_gate": "quick",
        },
    )
    state = {"code": {"raw_output": body}}
    veto = gate_llm_file_output_stage(
        stage=stage,
        state=state,
        result=body,
        artifact_key="code",
        backend="llm",
    )
    assert veto is None
