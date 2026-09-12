"""C0 frozen handoff fields + F3 write_stage_handoff + C1 gate_check."""
from __future__ import annotations

from types import SimpleNamespace

from core.harness.execution.stage_handoff import (
    HANDOFF_FIELDS,
    apply_gate_failure,
    attach_handoff,
    empty_handoff,
    format_handoff_regenerate_feedback,
    format_structured_artifact_block,
    gate_check,
    is_schema_gate_pause,
    normalize_handoff,
    schema_is_active,
    try_resume_schema_gate,
    write_stage_handoff,
)


def test_handoff_fields_frozen():
    assert HANDOFF_FIELDS == (
        "summary",
        "artifact_ref",
        "verify",
        "known_issues",
        "next",
    )


def test_normalize_and_attach():
    norm = normalize_handoff(
        {"summary": "done", "known_issues": "x", "extra": "drop"}
    )
    assert set(norm.keys()) == set(HANDOFF_FIELDS)
    assert "extra" not in norm
    assert norm["known_issues"] == ["x"]
    target: dict = {}
    attach_handoff(target, norm)
    assert target["handoff"]["summary"] == "done"
    assert empty_handoff()["known_issues"] == []


def test_schema_is_active():
    assert schema_is_active({}) is False
    assert schema_is_active(None) is False
    assert schema_is_active({"type": "object"}) is True


def test_write_stage_handoff_attaches_five_fields():
    stage = SimpleNamespace(
        id="s1",
        skill_name="code_generation",
        agent_id="programmer_agent",
        output_artifact="code",
        hitl=False,
        agent_name="Programmer",
    )
    nxt = SimpleNamespace(
        id="s2",
        output_artifact="test_cases",
        agent_name="QA",
        agent_id="qa_agent",
    )
    state: dict = {
        "code": {"raw_output": "## FILE: main.py\nprint(1)\n" * 20, "elapsed_sec": 1.2},
    }
    h = write_stage_handoff(
        state,
        stage=stage,
        artifact_key="code",
        sanitize_meta={"architecture": {"ok": False, "missing": 1}},
        status="ok",
        stages=[stage, nxt],
    )
    assert set(h.keys()) == set(HANDOFF_FIELDS)
    assert h["artifact_ref"] == "state:code"
    assert "code_generation" in h["summary"] or "code" in h["summary"]
    assert h["next"]
    assert state["code"]["handoff"]["summary"]
    assert state["_handoff"]["code"]["verify"]
    assert any("architecture" in x for x in h["known_issues"])


def test_write_failed_handoff_and_regenerate_feedback():
    stage = SimpleNamespace(
        id="s1",
        skill_name="requirement_analysis",
        agent_id="pm_agent",
        output_artifact="prd",
        hitl=True,
        agent_name="PM",
    )
    state: dict = {"prd": {"raw_output": "short", "status": "failed"}}
    h = write_stage_handoff(
        state,
        stage=stage,
        artifact_key="prd",
        status="failed",
        error="output too short",
        stages=[stage],
    )
    assert "failed" in h["summary"].lower() or "prd" in h["summary"]
    assert "output too short" in h["known_issues"]
    fb = format_handoff_regenerate_feedback(h)
    assert "[handoff]" in fb
    assert "known_issues:" in fb
    assert "next:" in fb


def test_gate_check_empty_schema_passes():
    stage = SimpleNamespace(
        id="s1",
        output_artifact="prd",
        input_schema={},
        output_schema={},
        gate_on_fail="block",
        handoff_required=False,
        input_artifacts=[],
    )
    r = gate_check(stage, {}, phase="input")
    assert r["ok"] is True and r["skipped"] is True
    r2 = gate_check(stage, {"prd": {"raw_output": "{}"}}, phase="output")
    assert r2["ok"] is True and r2["skipped"] is True


def test_gate_check_missing_required_blocks():
    stage = SimpleNamespace(
        id="arch",
        output_artifact="architecture",
        input_schema={},
        output_schema={
            "type": "object",
            "required": ["components", "architecture_mode"],
            "properties": {
                "components": {"type": "array"},
                "architecture_mode": {"type": "string"},
            },
        },
        gate_on_fail="block",
        handoff_required=False,
        input_artifacts=["prd"],
        hitl_phase="review",
    )
    state = {
        "architecture": {
            "raw_output": '{"architecture_mode": "code"}',
        }
    }
    r = gate_check(stage, state, phase="output")
    assert r["ok"] is False
    assert any("components" in e for e in r["errors"])
    assert r["action"] == "block"
    paused = apply_gate_failure(state, stage, r)
    assert paused is True
    assert state["phase"] == "paused"
    assert state["_hitl_phase_name"] == "schema_gate"


def test_gate_check_warn_only_continues():
    stage = SimpleNamespace(
        id="arch",
        output_artifact="architecture",
        output_schema={"type": "object", "required": ["components"]},
        gate_on_fail="",
        handoff_required=False,
        input_artifacts=[],
        skill_name="architecture_design",
        agent_id="architect_agent",
        hitl=False,
    )
    state = {"architecture": {"raw_output": "{}"}}
    r = gate_check(stage, state, phase="output")
    assert r["ok"] is False
    assert r["action"] == ""
    paused = apply_gate_failure(state, stage, r)
    assert paused is False
    assert state.get("phase") != "paused"
    assert not state.get("error")
    assert state.get("_schema_warnings")


def test_gate_check_input_required_upstream():
    stage = SimpleNamespace(
        id="code",
        output_artifact="code",
        input_schema={"type": "object", "required": ["prd"]},
        output_schema={},
        gate_on_fail="fail_pipeline",
        handoff_required=False,
        input_artifacts=["prd"],
    )
    r = gate_check(stage, {}, phase="input")
    assert r["ok"] is False
    assert any("prd" in e for e in r["errors"])
    state: dict = {}
    paused = apply_gate_failure(state, stage, r)
    assert paused is False
    assert state["phase"] == "failed"


def test_c2_apply_gate_failure_writes_hitl_audit():
    stage = SimpleNamespace(
        id="arch",
        output_artifact="architecture",
        output_schema={"type": "object", "required": ["components"]},
        gate_on_fail="hitl",
        handoff_required=False,
        input_artifacts=[],
        hitl_phase="review",
    )
    state = {"architecture": {"raw_output": "{}"}}
    r = gate_check(stage, state, phase="output")
    assert r["ok"] is False
    paused = apply_gate_failure(state, stage, r)
    assert paused is True
    assert state["_hitl_phase_name"] == "schema_gate"
    audit = state.get("_hitl_audit") or []
    assert audit
    assert audit[-1]["action"] == "schema_gate_hitl"
    assert is_schema_gate_pause(state)


def test_c2_try_resume_schema_gate_after_patch():
    stage = SimpleNamespace(
        id="arch",
        output_artifact="architecture",
        output_schema={
            "type": "object",
            "required": ["components"],
            "properties": {"components": {"type": "array"}},
        },
        gate_on_fail="hitl",
        handoff_required=False,
        input_artifacts=[],
    )
    state = {"architecture": {"raw_output": "{}"}}
    r = gate_check(stage, state, phase="output")
    apply_gate_failure(state, stage, r)
    # Human patches structured fields
    state["architecture"] = {"components": [{"name": "api"}], "raw_output": "{}"}
    res = try_resume_schema_gate(state, stage)
    assert res["ok"] is True and res["cleared"] is True
    assert state.get("phase") == "executing"
    assert not is_schema_gate_pause(state)
    actions = [a["action"] for a in (state.get("_hitl_audit") or [])]
    assert "schema_gate_resumed" in actions


def test_c2_try_resume_schema_gate_still_failing():
    stage = SimpleNamespace(
        id="arch",
        output_artifact="architecture",
        output_schema={"type": "object", "required": ["components"]},
        gate_on_fail="block",
        handoff_required=False,
        input_artifacts=[],
    )
    state = {"architecture": {"raw_output": "{}"}}
    apply_gate_failure(state, stage, gate_check(stage, state, phase="output"))
    res = try_resume_schema_gate(state, stage)
    assert res["ok"] is False
    assert state["phase"] == "paused"
    assert any(
        a["action"] == "schema_gate_resume_failed"
        for a in (state.get("_hitl_audit") or [])
    )


def test_c3_nested_input_schema_requires_functional_requirements():
    stage = SimpleNamespace(
        id="architect_agent",
        output_artifact="architecture",
        input_schema={
            "type": "object",
            "required": ["prd"],
            "properties": {
                "prd": {
                    "type": "object",
                    "required": ["functional_requirements"],
                    "properties": {
                        "functional_requirements": {"type": "array"},
                    },
                }
            },
        },
        output_schema={},
        gate_on_fail="hitl",
        handoff_required=False,
        input_artifacts=["prd"],
    )
    r = gate_check(stage, {"prd": {"title": "x", "raw_output": "# prd"}}, phase="input")
    assert r["ok"] is False
    assert any("functional_requirements" in e for e in r["errors"])
    state = {
        "prd": {
            "title": "x",
            "functional_requirements": [{"id": "FR-1", "name": "upload"}],
        }
    }
    r2 = gate_check(stage, state, phase="input")
    assert r2["ok"] is True


def test_c3_format_structured_artifact_block_prefers_fields():
    block = format_structured_artifact_block(
        "prd",
        {
            "title": "Video App",
            "functional_requirements": [{"id": "FR-1"}],
            "raw_output": "# long prose that must not be primary\n" * 20,
        },
    )
    assert "(structured)" in block
    assert "functional_requirements" in block
    assert "long prose" not in block


def test_c3_structured_ref_team_yaml_loads():
    from pathlib import Path
    import yaml

    path = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "teams"
        / "structured_ref.yaml"
    )
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    stages = data.get("stages") or []
    arch = next(s for s in stages if s.get("agent_id") == "architect_agent")
    assert arch.get("gate_on_fail") == "hitl"
    assert "prd" in (arch.get("input_schema") or {}).get("required", [])
