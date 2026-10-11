"""Unknown execution_type fail-closed + architecture_profile demote skip."""

from __future__ import annotations

import pytest

from core.harness.registry.execution_type_policy import (
    coerce_execution_type,
    execution_type_fail_closed,
)
from core.schemas_builder import PipelineStageConfig, apply_architecture_profile


def test_coerce_alias_llm_to_prompt():
    et, err = coerce_execution_type("llm", skill_name="s")
    assert err is None
    assert et == "prompt"


def test_coerce_known_handler():
    et, err = coerce_execution_type("handler", skill_name="s")
    assert err is None
    assert et == "handler"


def test_unknown_dev_soft_fallback(monkeypatch):
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", raising=False)
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", "1")
    et, err = coerce_execution_type("typo_mode", skill_name="s")
    assert err is None
    assert et == "prompt"


def test_unknown_fail_closed(monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", "1")
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", raising=False)
    et, err = coerce_execution_type("typo_mode", skill_name="s")
    assert et is None
    assert err and "unknown execution_type" in err
    assert "typo_mode" in err


def test_production_profile_fail_closed(monkeypatch):
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", raising=False)
    assert execution_type_fail_closed() is True
    et, err = coerce_execution_type("not_a_type", skill_name="x")
    assert et is None and err


@pytest.mark.asyncio
async def test_capability_demote_skips_when_architecture_profile_set():
    """Explicit architecture_profile must not be demoted by minimal capability."""
    from core.harness.execution.pipeline_stage import PipelineStageMixin

    stage = PipelineStageConfig(
        id="t",
        agent_id="demo_agent",
        skill_name="demo",
        execution_backend="agent",
        capability_profile="minimal",
        architecture_profile="react_tools",
    )
    apply_architecture_profile(stage)
    assert stage.execution_backend == "agent"

    mixin = PipelineStageMixin.__new__(PipelineStageMixin)
    await mixin._apply_capability_profile(stage, {})
    assert stage.execution_backend == "agent", "explicit architecture_profile must win"


@pytest.mark.asyncio
async def test_capability_demote_without_architecture_profile():
    from core.harness.execution.pipeline_stage import PipelineStageMixin

    stage = PipelineStageConfig(
        id="t",
        agent_id="demo_agent",
        skill_name="demo",
        execution_backend="agent",
        capability_profile="minimal",
        architecture_profile="",
    )
    mixin = PipelineStageMixin.__new__(PipelineStageMixin)
    await mixin._apply_capability_profile(stage, {})
    assert stage.execution_backend == "llm"


def test_decision_matrix_lists_architecture_profiles():
    """Living Spec drift guard: doc must name every ARCHITECTURE_PROFILES key."""
    from pathlib import Path

    from core.schemas_builder import ARCHITECTURE_PROFILES

    root = Path(__file__).resolve().parents[5]
    doc = root / "docs" / "architecture" / "execution-decision-matrix.md"
    text = doc.read_text(encoding="utf-8")
    for key in ARCHITECTURE_PROFILES:
        assert key in text, f"missing architecture_profile={key} in {doc}"
