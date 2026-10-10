"""Coding closed-loop defaults for uses_file_output stages (config-driven)."""

from __future__ import annotations

import os

from core.schemas_builder import PipelineStageConfig, apply_coding_stage_defaults


def test_file_output_enables_sandbox_and_autoreview(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_SANDBOX", "true")
    monkeypatch.setenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "true")
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        sandbox=False,
        review_gate="quick",
    )
    assert stage.sandbox is True
    assert "autoreview" in (stage.required_skills or [])
    assert isinstance(stage.done_verify, dict) and stage.done_verify.get("enabled") is True


def test_sandbox_mode_none_opts_out(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_SANDBOX", "true")
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        sandbox=False,
        sandbox_mode="none",
    )
    assert stage.sandbox is False


def test_review_gate_none_skips_autoreview(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "true")
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        review_gate="none",
        required_skills=[],
    )
    assert "autoreview" not in (stage.required_skills or [])


def test_non_coding_unchanged():
    stage = PipelineStageConfig(
        id="pm",
        agent_id="pm_agent",
        uses_file_output=False,
        sandbox=False,
    )
    assert stage.sandbox is False
    assert "autoreview" not in (stage.required_skills or [])


def test_apply_helper_idempotent(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_SANDBOX", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
        sandbox=True,
        required_skills=["autoreview"],
        done_verify={"enabled": True, "min_output_length": 40},
    )
    again = apply_coding_stage_defaults(stage)
    assert again.done_verify.get("min_output_length") == 40
    assert again.required_skills.count("autoreview") == 1
