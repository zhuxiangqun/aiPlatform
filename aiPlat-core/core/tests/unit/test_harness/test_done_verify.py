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


def test_missing_completion_standard_does_not_fail_open(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    monkeypatch.setenv("AIPLAT_DONE_VERIFY_FAIL_OPEN", "1")
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    loop = ReActLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "x" * 80,
            "_done_verify": {
                "require_completion_standard": True,
                "min_output_length": 10,
                "reject_trivial_done": False,
            },
            "_done_verify_veto_count": 2,
            "_bound_skill_ids": [],
        },
        step_count=3,
    )
    reason = loop._acceptance_gate(state)
    assert reason and "completion standard" in reason


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


def test_require_review_forces_autoreview_even_if_unbound(monkeypatch):
    """SOP Step 5: require_review must not silently skip when autoreview unbound."""
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify(
        {
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_bound_skill_ids": ["code_generation"],
            "_followup_skills_done": [],
            "_done_verify": {
                "min_output_length": 10,
                "reject_trivial_done": False,
                "reject_action_envelope": False,
                "require_substrings": ["## FILE:"],
                "review_gate": "quick",
                "require_review": True,
            },
        }
    )
    assert blocked and "autoreview" in blocked
    ok = run_done_verify(
        {
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_bound_skill_ids": ["code_generation"],
            "_followup_skills_done": ["autoreview"],
            "_done_verify": {
                "min_output_length": 10,
                "reject_trivial_done": False,
                "reject_action_envelope": False,
                "require_substrings": ["## FILE:"],
                "review_gate": "quick",
                "require_review": True,
            },
        }
    )
    assert ok is None


def test_require_review_ignores_none_gate_and_passed_flag(monkeypatch):
    """review_gate=none and _review_gate_passed must not waive SOP Step 5."""
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify(
        {
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_bound_skill_ids": ["code_generation"],
            "_followup_skills_done": [],
            "_review_gate_passed": True,
            "_done_verify": {
                "min_output_length": 10,
                "reject_trivial_done": False,
                "reject_action_envelope": False,
                "require_substrings": ["## FILE:"],
                "review_gate": "none",
                "require_review": True,
            },
        }
    )
    assert blocked and "autoreview" in blocked


def test_require_review_not_satisfied_by_hygiene_peer(monkeypatch):
    """code-hygiene completion is not an autoreview receipt."""
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify(
        {
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_bound_skill_ids": ["code_generation", "code-hygiene"],
            "_followup_skills_done": ["code-hygiene"],
            "_done_verify": {
                "min_output_length": 10,
                "reject_trivial_done": False,
                "reject_action_envelope": False,
                "require_substrings": ["## FILE:"],
                "review_gate": "quick",
                "require_review": True,
            },
        }
    )
    assert blocked and "autoreview" in blocked
    rejected = run_done_verify(
        {
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_followup_skills_done": ["autoreview"],
            "_require_review_incomplete": True,
            "_done_verify": {
                "min_output_length": 10,
                "reject_trivial_done": False,
                "reject_action_envelope": False,
                "require_substrings": ["## FILE:"],
                "review_gate": "quick",
                "require_review": True,
            },
        }
    )
    assert rejected and "rejected" in rejected


def test_require_review_veto_is_hard():
    from core.harness.execution.done_verify import is_hard_done_veto

    reason = "done_verify: review_gate=quick requires follow-up skill `autoreview` before DONE"
    # Missing follow-up receipt must not fail-open after soft vetoes (soft or hard).
    assert is_hard_done_veto(reason) is True
    assert is_hard_done_veto(reason, {"_done_verify": {"require_review": True}}) is True
    assert is_hard_done_veto(
        "done_verify: require_review — empty diff is not an autoreview receipt",
        {"_done_verify": {"require_review": True}},
    ) is True
    assert is_hard_done_veto(
        "done_verify: empty diff is not an autoreview receipt",
    ) is True
    assert is_hard_done_veto(
        "done_verify: review_gate follow-up `autoreview` "
        "approval_required is not a review receipt",
    ) is True
    assert is_hard_done_veto(
        "done_verify: verify ring failed (exception; fail-closed for coding/review)"
    ) is True


def test_acceptance_gate_env_off_still_runs_done_verify(monkeypatch):
    """File-contract switch must not skip the DONE ring."""
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    monkeypatch.setenv("AIPLAT_ACCEPTANCE_GATE_ENABLED", "false")
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


def test_done_verify_exception_is_hard_helper():
    from core.harness.execution.done_verify import done_verify_exception_is_hard

    assert done_verify_exception_is_hard(
        {"_done_verify": {"require_review": True}}
    ) is True
    assert done_verify_exception_is_hard({"_skill_delivery": "once"}) is True
    assert done_verify_exception_is_hard(
        {"_bound_skill_ids": ["code_generation", "autoreview"]}
    ) is True
    assert done_verify_exception_is_hard(
        {"_bound_skill_ids": ["chitchat"], "_done_verify": {"min_output_length": 0}}
    ) is False


def test_plan_done_verify_exception_fail_closed(monkeypatch):
    from core.harness.execution.loop._facade import PlanExecuteLoop

    loop = PlanExecuteLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_done_verify": {"require_review": True},
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_skill_delivery": "once",
        },
        step_count=1,
    )

    def _boom(_ctx):
        raise RuntimeError("plan verify boom")

    monkeypatch.setattr(
        "core.harness.execution.done_verify.run_done_verify",
        _boom,
    )
    reason = loop._plan_done_verify_reason(state)
    assert reason and "verify ring failed" in reason


def test_done_verify_exception_fail_closed_for_coding(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    monkeypatch.setenv("AIPLAT_ACCEPTANCE_GATE_ENABLED", "true")
    loop = ReActLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_done_verify": {"require_review": True, "min_output_length": 10},
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_skill_delivery": "once",
            "_acceptance_veto_count": 3,
            "_primary_skill_delivered": True,
            "_followup_skills_done": ["autoreview"],
        },
        step_count=1,
    )

    def _boom(_ctx):
        raise RuntimeError("verify boom")

    monkeypatch.setattr(
        "core.harness.execution.done_verify.run_done_verify",
        _boom,
    )
    reason = loop._acceptance_gate(state)
    assert reason and "verify ring failed" in reason
    seal = loop._done_verify_seal_reason(state)
    assert seal and "verify ring failed" in seal


def test_done_verify_exception_fail_open_for_chat(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    loop = ReActLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "hello there, this is a chat reply " + ("y" * 40),
            "_done_verify": {"min_output_length": 0, "reject_trivial_done": False},
            "_bound_skill_ids": ["chitchat"],
        },
        step_count=1,
    )

    def _boom(_ctx):
        raise RuntimeError("verify boom")

    monkeypatch.setattr(
        "core.harness.execution.done_verify.run_done_verify",
        _boom,
    )
    assert loop._done_verify_seal_reason(state) is None


def test_delivery_without_standard_cannot_finish(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    reason = run_done_verify({
        "output": "x" * 80,
        "_done_verify": {
            "require_completion_standard": True,
            "require_testability": True,
            "min_output_length": 20,
            "reject_trivial_done": False,
        },
    })
    assert reason and "completion standard" in reason


def test_feature_flag_required_before_done(monkeypatch):
    from core.harness.execution.done_verify import feature_flag_missing

    assert feature_flag_missing({"output": "## FILE: a.py"})
    assert feature_flag_missing({
        "output": "FEATURE_NEW_ORDER_FLOW=true wraps the new path",
    }) is None
    assert feature_flag_missing({"output": "先开 5% 灰度 canary"}) is None
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_done_verify": {
            "require_feature_flag": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert blocked and "feature flag" in blocked
    ok = run_done_verify({
        "output": "feature flag USE_NEW_ORDER_FLOW\n## FILE: a.py\n" + ("x" * 20),
        "_done_verify": {
            "require_feature_flag": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert ok is None


def test_rollback_checkpoint_required_before_done(monkeypatch):
    from core.harness.execution.done_verify import rollback_checkpoint_missing

    assert rollback_checkpoint_missing({"output": "## FILE: a.py"})
    assert rollback_checkpoint_missing({
        "_file_checkpoints": [{"id": "abc123", "path": "/tmp/a.py"}],
    }) is None
    assert rollback_checkpoint_missing({
        "output": "git tag before-refactoring-order-service",
    }) is None
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_done_verify": {
            "require_rollback_checkpoint": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert blocked and "rollback checkpoint" in blocked
    ok = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 20),
        "_file_checkpoints": [{"id": "ck1", "path": "a.py"}],
        "_done_verify": {
            "require_rollback_checkpoint": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert ok is None


def test_rollback_command_required_before_done(monkeypatch):
    from core.harness.execution.done_verify import rollback_command_missing

    assert rollback_command_missing({"output": "## FILE: a.py"})
    assert rollback_command_missing({
        "output": "git checkout before-refactoring-order-service -- src/a.ts",
    }) is None
    assert rollback_command_missing({
        "output": "FEATURE_NEW_ORDER_FLOW=false npm run build",
    }) is None
    assert rollback_command_missing({"output": "## 回滚命令\ngit reset --hard tag"}) is None
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_done_verify": {
            "require_rollback_command": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert blocked and "rollback command" in blocked
    ok = run_done_verify({
        "output": "git reset --hard before-refactor\n## FILE: a.py\n" + ("x" * 20),
        "_done_verify": {
            "require_rollback_command": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert ok is None


def test_dependency_map_required_before_done(monkeypatch):
    from core.harness.execution.done_verify import dependency_map_missing

    assert dependency_map_missing({"output": "安全区: a.ts"})
    assert dependency_map_missing({
        "output": "安全区: order-service.ts\n保护区: payment-cache.ts",
    }) is None
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_done_verify": {
            "require_dependency_map": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert blocked and "dependency map" in blocked
    ok = run_done_verify({
        "output": "safe zone: a.py\nprotected zone: shared.py\n## FILE: a.py\n" + ("x" * 20),
        "_done_verify": {
            "require_dependency_map": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert ok is None


def test_refactor_plan_required_before_done(monkeypatch):
    from core.harness.execution.done_verify import refactor_plan_missing

    assert refactor_plan_missing({"output": "## FILE: a.py"})
    assert refactor_plan_missing({"output": "## Refactor Plan\n- split createOrder"}) is None
    assert refactor_plan_missing({"output": "## 重构计划\n- 拆分职责"}) is None
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_done_verify": {
            "require_refactor_plan": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert blocked and "refactor plan" in blocked
    ok = run_done_verify({
        "output": "## Refactor Plan\n- keep API\n## FILE: a.py\n" + ("x" * 20),
        "_done_verify": {
            "require_refactor_plan": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert ok is None


def test_diagnosis_list_required_before_done(monkeypatch):
    from core.harness.execution.done_verify import diagnosis_list_missing

    assert diagnosis_list_missing({"output": "## FILE: a.py"})
    assert diagnosis_list_missing({"output": "[P1] order.ts:40 → n+1 query"}) is None
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_done_verify": {
            "require_diagnosis": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert blocked and "diagnosis list" in blocked
    ok = run_done_verify({
        "output": "[P0] a.py:12 → swallows errors\n## FILE: a.py\n" + ("x" * 20),
        "_done_verify": {
            "require_diagnosis": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert ok is None


def test_tdd_enforce_needs_passing_test_receipt(monkeypatch):
    from core.harness.execution.done_verify import tdd_evidence_missing

    assert tdd_evidence_missing({}) and "run tests" in tdd_evidence_missing({})
    assert tdd_evidence_missing({
        "_tool_receipts": [{"tool": "bash", "status": "failed", "detail": "pytest -q"}],
    }) and "failed" in tdd_evidence_missing({
        "_tool_receipts": [{"tool": "bash", "status": "failed", "detail": "pytest -q"}],
    })
    assert tdd_evidence_missing({
        "_tool_receipts": [{"tool": "bash", "status": "ok", "detail": "pytest -q\n2 passed"}],
    }) is None
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    blocked = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_done_verify": {
            "require_tdd": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert blocked and "tdd_enforce" in blocked
    ok = run_done_verify({
        "output": "## FILE: a.py\n" + ("x" * 40),
        "_tool_receipts": [{"tool": "bash", "status": "ok", "detail": "pytest core/tests -q"}],
        "_done_verify": {
            "require_tdd": True,
            "require_substrings": ["## FILE:"],
            "min_output_length": 10,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert ok is None


def test_output_schema_counts_as_completion_standard(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    reason = run_done_verify({
        "output": "x" * 80,
        "output_schema": {"type": "object"},
        "_done_verify": {
            "require_completion_standard": True,
            "min_output_length": 20,
            "reject_trivial_done": False,
            "reject_action_envelope": False,
        },
    })
    assert reason is None
