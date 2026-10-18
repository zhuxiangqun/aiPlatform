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
        output_schema={"type": "object"},
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
        output_schema={"type": "object"},
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


def test_llm_file_output_require_review_cannot_skip():
    """SOP Step 5: oneshot llm must not drop a hard autoreview requirement."""
    body = "## FILE: src/app.tsx\n" + ("export const x = 1;\n" * 8)
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
            "require_review": True,
            "review_gate": "quick",
            "require_substrings": ["## FILE:"],
        },
        output_schema={"type": "object"},
    )
    state = {"code": {"raw_output": body}}
    veto = gate_llm_file_output_stage(
        stage=stage,
        state=state,
        result=body,
        artifact_key="code",
        backend="llm",
    )
    assert veto and "require_review" in veto
    assert "execution_backend=agent" in veto
    assert state["code"].get("status") == "failed"


def test_llm_file_output_keeps_only_highest_repair_candidate():
    import json

    winner = "## FILE: src/app.tsx\nexport const x = 1;\n" * 2
    loser = "patch-a should not deploy"
    body = (
        "## REPAIR_CANDIDATES\n```json\n"
        + json.dumps(
            [
                {"id": "a", "score": 0.1, "text": loser},
                {"id": "b", "score": 0.9, "text": winner},
            ]
        )
        + "\n```\n"
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
            "reject_trivial_done": False,
            "require_testability": False,
            "require_completion_standard": False,
            "review_gate": "none",
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
    assert state["code"]["raw_output"] == winner
    assert "patch-a" not in state["code"]["raw_output"]
    assert state["_selected_repair_output"] == winner


def test_llm_fix_claim_without_receipt_vetoes_before_deploy():
    """Do not prefix ## FILE: blobs; an unbacked fix claim fails the stage."""
    body = (
        "## FILE: skills/demo/handler.py\n"
        "async def execute(params):\n"
        "    return {'ok': True}\n"
        "已经修好了\n"
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
            "reject_trivial_done": False,
            "require_testability": False,
            "require_completion_standard": False,
            "review_gate": "none",
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
    assert veto and "completion receipt" in veto
    assert state["code"]["raw_output"] == body
    assert state["code"].get("status") == "failed"


def test_file_output_default_file_marker_satisfies_standard():
    from core.harness.execution.done_verify import missing_completion_standard_reason

    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        execution_backend="llm",
        output_artifact="code",
    )
    assert missing_completion_standard_reason(stage) is None
    assert "## FILE:" in (stage.done_verify.get("require_substrings") or [])


def test_file_output_explicit_empty_standard_still_blocks():
    from core.harness.execution.done_verify import missing_completion_standard_reason

    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        execution_backend="llm",
        output_artifact="code",
        done_verify={
            "enabled": True,
            "require_completion_standard": True,
            "require_substrings": [],
            "require_testability": False,
            "min_output_length": 20,
            "reject_trivial_done": False,
        },
    )
    reason = missing_completion_standard_reason(stage)
    assert reason and "completion standard" in reason

    stage.output_schema = {"type": "object"}
    assert missing_completion_standard_reason(stage) is None
