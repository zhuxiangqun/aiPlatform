"""DONE Verify ring — config-driven completion checks before DONE."""

from __future__ import annotations

import os

import pytest

from core.harness.execution.done_verify import (
    build_done_verify_config,
    done_verify_enabled,
    run_done_verify,
)
from core.harness.execution.loop._facade import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum


def test_build_merges_quality_gate_and_expected():
    cfg = build_done_verify_config(
        quality_gate={"min_output_length": 80},
        expected_outcomes=[{"field": "status", "constraint": "equals", "expected": "ok"}],
        review_gate="quick",
    )
    assert cfg["min_output_length"] == 80
    assert cfg["expected_outcomes"][0]["field"] == "status"
    assert cfg["review_gate"] == "quick"


def test_reject_trivial_done(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    reason = run_done_verify({"output": "DONE", "_done_verify": {"min_output_length": 0}})
    assert reason and "trivial" in reason


def test_min_output_length(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    reason = run_done_verify(
        {
            "output": "short",
            "_done_verify": {"min_output_length": 40, "reject_trivial_done": False},
        }
    )
    assert reason and "min_output_length=40" in reason


def test_expected_outcomes_json(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    ok = run_done_verify(
        {
            "output": '{"status":"ok","score":1}',
            "_done_verify": {
                "min_output_length": 1,
                "reject_trivial_done": False,
                "expected_outcomes": [
                    {"field": "status", "constraint": "equals", "expected": "ok"},
                ],
            },
        }
    )
    assert ok is None
    bad = run_done_verify(
        {
            "output": '{"status":"fail"}',
            "_done_verify": {
                "min_output_length": 1,
                "reject_trivial_done": False,
                "expected_outcomes": [
                    {"field": "status", "constraint": "equals", "expected": "ok"},
                ],
            },
        }
    )
    assert bad and "expected_outcomes" in bad


def test_require_keys(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    reason = run_done_verify(
        {
            "output": '{"a":1}',
            "_done_verify": {
                "min_output_length": 1,
                "reject_trivial_done": False,
                "require_keys": ["a", "b"],
            },
        }
    )
    assert reason and "missing required keys" in reason


def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "false")
    assert done_verify_enabled({}) is False
    assert run_done_verify({"output": "DONE"}) is None


def test_acceptance_gate_wires_done_verify(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    monkeypatch.setenv("AIPLAT_ACCEPTANCE_GATE_ENABLED", "true")
    loop = ReActLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "DONE",
            "_done_verify": {"min_output_length": 0},
            "_bound_skill_ids": ["chitchat"],
        },
        step_count=1,
    )
    reason = loop._acceptance_gate(state)
    assert reason and reason.startswith("done_verify:")


def test_acceptance_gate_fail_open_after_two_verify_vetoes(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_DONE_VERIFY_FAIL_CLOSED", raising=False)
    monkeypatch.delenv("AIPLAT_DONE_VERIFY_FAIL_OPEN", raising=False)
    loop = ReActLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "x",
            "_done_verify": {"min_output_length": 100, "reject_trivial_done": False},
            "_done_verify_veto_count": 2,
            "_bound_skill_ids": [],
        },
        step_count=3,
    )
    assert loop._acceptance_gate(state) is None
    assert state.context.get("_done_verify_exhausted") is True


def test_acceptance_gate_fail_closed_in_production_after_two_vetoes(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.delenv("AIPLAT_DONE_VERIFY_FAIL_OPEN", raising=False)
    loop = ReActLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "x",
            "_done_verify": {"min_output_length": 100, "reject_trivial_done": False},
            "_done_verify_veto_count": 2,
            "_bound_skill_ids": [],
        },
        step_count=3,
    )
    reason = loop._acceptance_gate(state)
    assert reason and "done_verify" in reason
    assert state.context.get("_done_verify_exhausted") is True


def test_apply_acceptance_veto_bumps_done_verify_counter():
    loop = ReActLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={"messages": []},
        step_count=1,
    )
    loop._apply_acceptance_veto(state, "done_verify: output length 1 < min_output_length=20")
    assert state.context["_done_verify_veto_count"] == 1
    assert state.current == LoopStateEnum.REASONING


def test_review_gate_requires_bound_followup(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify(
        {
            "output": "implemented fix with full explanation " + ("x" * 40),
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_followup_skills_done": [],
            "_done_verify": {
                "min_output_length": 20,
                "reject_trivial_done": False,
                "review_gate": "required",
            },
        }
    )
    assert blocked and "review_gate" in blocked and "autoreview" in blocked
    ok = run_done_verify(
        {
            "output": "implemented fix with full explanation " + ("x" * 40),
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_followup_skills_done": ["autoreview"],
            "_done_verify": {
                "min_output_length": 20,
                "reject_trivial_done": False,
                "review_gate": "required",
            },
        }
    )
    assert ok is None


def test_require_commands_exit_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    reason = run_done_verify(
        {
            "output": "body " + ("y" * 40),
            "cwd": str(tmp_path),
            "_done_verify": {
                "min_output_length": 10,
                "reject_trivial_done": False,
                "require_commands": ["false"],
            },
        }
    )
    assert reason and "require_commands" in reason


def test_review_gate_noop_without_bound_skill(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    assert (
        run_done_verify(
            {
                "output": "plain answer " + ("z" * 40),
                "_bound_skill_ids": ["chitchat"],
                "_done_verify": {
                    "min_output_length": 10,
                    "reject_trivial_done": False,
                    "review_gate": "required",
                },
            }
        )
        is None
    )
