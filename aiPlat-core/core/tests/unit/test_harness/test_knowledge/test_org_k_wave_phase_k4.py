"""Phase K4 — OrgRun / tool-streak cases; no TBox; no SKILL.md."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.apps.fde.service.k_wave_case import record_case_from_org_run, record_case_from_tool_streak
from core.harness.infrastructure.hooks.on_error_reflector import OnErrorReflector


def test_org_run_case_overlay(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ONTOLOGY_CASE_LEARNING", raising=False)
    run = {
        "run_id": "run-k4",
        "trace_id": "run-k4",
        "trace_origin": "run",
        "goal_id": "g1",
        "domain_id": "it-ops",
        "status": "succeeded",
        "exceptions": [],
        "reasoning": {"path_count": 2, "entities": [{"entity_id": "e1"}]},
    }
    out = record_case_from_org_run(run)
    assert out.get("status") == "ok"
    assert out.get("case_id")
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    store = OntologyCaseStore("it-ops")
    cases = store._load()
    case = cases[out["case_id"]]
    assert case.metadata.get("skill_candidate") is True
    assert case.metadata.get("trace_id") == "run-k4"
    assert "org_run" in case.tags
    # no skill file
    assert not list(tmp_path.rglob("SKILL.md"))


def test_tool_streak_case(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = record_case_from_tool_streak(
        domain_id="it-ops",
        tool_name="fetch",
        error_code="timeout",
        run_id="r1",
        trace_id="r1",
        task="t",
        detail="boom",
    )
    assert out.get("status") == "ok"
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    case = OntologyCaseStore("it-ops")._load()[out["case_id"]]
    assert case.outcome == "failure"
    assert case.metadata.get("skill_candidate") is False


@pytest.mark.asyncio
async def test_reflector_same_tool_error_writes_case(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    recorded = []

    def _rec(**kwargs):
        recorded.append(kwargs)
        return {"status": "ok", "case_id": "c1"}

    monkeypatch.setattr(
        "core.apps.fde.service.k_wave_case.record_case_from_tool_streak",
        _rec,
    )

    async def _hint(_self, _ctx):
        return "change approach"

    monkeypatch.setattr(OnErrorReflector, "_generate_reflection", _hint)

    reflector = OnErrorReflector()
    reflector._enabled = True

    ctx1 = SimpleNamespace(
        tool_result={"error": "timeout", "tool_name": "fetch"},
        task="same-task",
        last_error="timeout",
        domain_id="it-ops",
        run_id="r9",
        trace_id="r9",
    )
    assert await reflector.on_post_observe(ctx1) is None
    assert recorded == []
    out = await reflector.on_post_observe(ctx1)
    assert out and out.get("reasoning_hint")
    assert len(recorded) == 1
    assert recorded[0]["tool_name"] == "fetch"
    assert recorded[0]["error_code"] == "timeout"

    # different error resets streak
    ctx2 = SimpleNamespace(
        tool_result={"error": "denied", "tool_name": "fetch"},
        task="same-task",
        last_error="denied",
        domain_id="it-ops",
        run_id="r9",
        trace_id="r9",
    )
    assert await reflector.on_post_observe(ctx2) is None
    assert len(recorded) == 1
