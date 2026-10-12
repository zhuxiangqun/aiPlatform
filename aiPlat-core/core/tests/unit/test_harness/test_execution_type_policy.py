"""Unknown execution_type fail-closed (default) + FAIL_OPEN E5 + demote skip."""

from __future__ import annotations

import pytest

from core.harness.registry.execution_type_policy import (
    coerce_execution_type,
    execution_type_fail_closed,
    fail_open_governance_status,
    record_fail_open_audit,
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


def test_default_fail_closed(monkeypatch):
    """Safe default: no env → hard-fail unknown types (no silent LLM)."""
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_SOFT_DEV", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_REASON", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_BY", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_UNTIL", raising=False)
    assert execution_type_fail_closed() is True
    et, err = coerce_execution_type("typo_mode", skill_name="s")
    assert et is None
    assert err and "unknown execution_type" in err


def test_soft_dev_opt_in(monkeypatch):
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", raising=False)
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_SOFT_DEV", "1")
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", raising=False)
    assert execution_type_fail_closed() is False
    et, err = coerce_execution_type("typo_mode", skill_name="s")
    assert err is None
    assert et == "prompt"


def test_fail_closed_explicit_false(monkeypatch):
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_SOFT_DEV", raising=False)
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", "0")
    assert execution_type_fail_closed() is False


def test_fail_open_without_governance_stays_closed(monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", "1")
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_REASON", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_BY", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_UNTIL", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_SOFT_DEV", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", raising=False)
    gov = fail_open_governance_status()
    assert gov["flag"] is True
    assert gov["authorized"] is False
    assert execution_type_fail_closed() is True


def test_fail_open_authorized(monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", "1")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_REASON", "incident-42 hotfix")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_BY", "ops@example.com")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_UNTIL", "2099-01-01T00:00:00+00:00")
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_SOFT_DEV", raising=False)
    assert fail_open_governance_status()["authorized"] is True
    assert execution_type_fail_closed() is False
    et, err = coerce_execution_type("typo_mode", skill_name="s")
    assert err is None and et == "prompt"


def test_fail_open_expired(monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", "1")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_REASON", "old")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_BY", "ops")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_UNTIL", "2020-01-01T00:00:00Z")
    assert fail_open_governance_status()["expired"] is True
    assert fail_open_governance_status()["authorized"] is False
    assert execution_type_fail_closed() is True


def test_fail_open_expires_within_24h(monkeypatch):
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", "1")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_REASON", "incident-near-expiry")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_BY", "ops@example.com")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_UNTIL", soon)
    st = fail_open_governance_status()
    assert st["authorized"] is True
    assert st["expires_within_24h"] is True


def test_record_fail_open_sidecar(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", "1")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_REASON", "test")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_BY", "tester")
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN_UNTIL", "2099-06-01T12:00:00Z")
    st = record_fail_open_audit(source="test")
    assert st["authorized"] is True
    side = tmp_path / "ops" / "execution_type_fail_open.json"
    assert side.is_file()


def test_unknown_fail_closed_explicit(monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", "1")
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_SOFT_DEV", raising=False)
    et, err = coerce_execution_type("typo_mode", skill_name="s")
    assert et is None
    assert err and "unknown execution_type" in err
    assert "typo_mode" in err


def test_production_profile_still_fail_closed(monkeypatch):
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_OPEN", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_FAIL_CLOSED", raising=False)
    monkeypatch.delenv("AIPLAT_EXECUTION_TYPE_SOFT_DEV", raising=False)
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
async def test_capability_demote_skips_explicit_execution_backend():
    """Bare execution_backend=agent (schema default is llm) must not demote."""
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
    state: dict = {}
    await mixin._apply_capability_profile(stage, state)
    assert stage.execution_backend == "agent"
    assert state.get("_capability_demote_skipped") == "explicit_execution_backend"


def test_decision_matrix_lists_architecture_profiles():
    """Living Spec drift guard: doc must name every ARCHITECTURE_PROFILES key."""
    from pathlib import Path

    from core.schemas_builder import ARCHITECTURE_PROFILES

    root = Path(__file__).resolve().parents[5]
    doc = root / "docs" / "architecture" / "execution-decision-matrix.md"
    text = doc.read_text(encoding="utf-8")
    for key in ARCHITECTURE_PROFILES:
        assert key in text, f"missing architecture_profile={key} in {doc}"
