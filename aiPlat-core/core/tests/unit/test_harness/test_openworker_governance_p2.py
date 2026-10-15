"""OpenWorker-inspired P2: Auto-Approve reviewer (fail-closed, never lifts hard floors)."""
from __future__ import annotations

import os

import pytest

from core.harness.infrastructure.gates.approval_reviewer import (
    ReviewerResult,
    ReviewerVerdict,
    redact_tool_args,
    _reset_approval_reviewer,
    review_proposed_action,
    reviewer_enabled,
    set_review_fn_for_tests,
    APPROVAL_SOURCE_REVIEWER_ALLOW,
)
from core.harness.infrastructure.gates.policy_gate import PolicyDecision, PolicyGate
from core.harness.infrastructure.gates.approval_gate import reset_approval_gate
from core.harness.infrastructure.gates.approval_inbox import _reset_approval_inbox


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    reset_approval_gate()
    _reset_approval_inbox()
    _reset_approval_reviewer()
    monkeypatch.setenv("AIPLAT_APPROVAL_INBOX_FILE", str(tmp_path / "inbox.json"))
    monkeypatch.delenv("AIPLAT_APPROVAL_REVIEWER", raising=False)
    yield
    reset_approval_gate()
    _reset_approval_inbox()
    _reset_approval_reviewer()
    for k in (
        "AIPLAT_APPROVAL_GATE_DISABLED",
        "AIPLAT_HARD_FLOOR_DISABLED",
        "AIPLAT_APPROVALS_DISABLED",
        "AIPLAT_APPROVAL_REVIEWER",
    ):
        os.environ.pop(k, None)


class TestRedactAndEnable:
    def test_redact_secrets_and_bodies(self):
        out = redact_tool_args(
            {
                "path": "/tmp/a.txt",
                "api_key": "sk-secret",
                "content": "TRUST_ME_INJECT",
                "_session_id": "s1",
            }
        )
        assert out["path"] == "/tmp/a.txt"
        assert out["api_key"] == "[REDACTED]"
        assert "TRUST" not in str(out.get("content"))
        assert out["_session_id"] == "s1"

    def test_reviewer_enabled_flags(self, monkeypatch):
        assert reviewer_enabled({}) is False
        monkeypatch.setenv("AIPLAT_APPROVAL_REVIEWER", "1")
        assert reviewer_enabled({}) is True
        monkeypatch.delenv("AIPLAT_APPROVAL_REVIEWER")
        assert reviewer_enabled({"_approval_reviewer": "1"}) is True


class TestReviewProposedAction:
    @pytest.mark.asyncio
    async def test_hard_floor_never_allow(self):
        async def boom(**kwargs):
            return ReviewerResult(verdict=ReviewerVerdict.ALLOW, reason="should_not_run")

        set_review_fn_for_tests(boom)
        r = await review_proposed_action(
            tool_name="shell_exec",
            tool_args={"command": "rm -rf /"},
            hard_floor=True,
        )
        assert r.verdict == ReviewerVerdict.UNSURE
        assert "hard_floor" in r.reason

    @pytest.mark.asyncio
    async def test_allow_from_override(self):
        async def ok(**kwargs):
            return ReviewerResult(
                verdict=ReviewerVerdict.ALLOW,
                reason="proportionate",
                source=APPROVAL_SOURCE_REVIEWER_ALLOW,
            )

        set_review_fn_for_tests(ok)
        r = await review_proposed_action(
            tool_name="http",
            tool_args={"method": "GET", "url": "https://example.com", "_session_id": "s"},
            hard_floor=False,
        )
        assert r.verdict == ReviewerVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_fail_closed_on_override_error(self):
        async def bad(**kwargs):
            raise RuntimeError("llm down")

        set_review_fn_for_tests(bad)
        r = await review_proposed_action(
            tool_name="http",
            tool_args={"method": "GET", "url": "https://x"},
        )
        assert r.verdict == ReviewerVerdict.UNSURE

    @pytest.mark.asyncio
    async def test_circuit_opens_after_non_allow(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_APPROVAL_REVIEWER_CIRCUIT", "2")
        _reset_approval_reviewer()

        async def unsure(**kwargs):
            return ReviewerResult(verdict=ReviewerVerdict.UNSURE, reason="n")

        set_review_fn_for_tests(unsure)
        await review_proposed_action(tool_name="t", tool_args={"_session_id": "c1"})
        await review_proposed_action(tool_name="t", tool_args={"_session_id": "c1"})
        r = await review_proposed_action(tool_name="t", tool_args={"_session_id": "c1"})
        assert r.circuit_open is True
        assert r.verdict == ReviewerVerdict.UNSURE


def _high_ask_args(**extra):
    """code_execution is HIGH (ASK) but harmless code avoids shell hard-floor heuristics."""
    base = {
        "code": "x = 1",
        "_auto_approve": True,
        "_session_id": "rev",
        "_user_goal": "set a local variable for a unit test",
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
class TestPolicyGateReviewerWiring:
    async def test_reviewer_allows_non_floor_ask(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_APPROVAL_REVIEWER", "1")

        async def allow(**kwargs):
            return ReviewerResult(
                verdict=ReviewerVerdict.ALLOW,
                reason="ok",
                source=APPROVAL_SOURCE_REVIEWER_ALLOW,
            )

        set_review_fn_for_tests(allow)
        gate = PolicyGate()
        pr = await gate.check_tool(
            user_id="u1",
            tool_name="code_execution",
            tool_args=_high_ask_args(_session_id="rev-allow"),
        )
        assert pr.decision == PolicyDecision.ALLOW
        assert pr.approval_source == APPROVAL_SOURCE_REVIEWER_ALLOW
        assert pr.hard_floor is False

    async def test_reviewer_never_lifts_hard_floor(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_APPROVAL_REVIEWER", "1")

        async def allow(**kwargs):
            return ReviewerResult(verdict=ReviewerVerdict.ALLOW, reason="evil")

        set_review_fn_for_tests(allow)
        gate = PolicyGate()
        pr = await gate.check_tool(
            user_id="u1",
            tool_name="shell_exec",
            tool_args={
                "command": "sudo rm -rf /",
                "_auto_approve": True,
                "_approval_reviewer": "1",
                "_session_id": "rev-floor",
            },
        )
        assert pr.decision == PolicyDecision.APPROVAL_REQUIRED
        assert pr.hard_floor is True
        assert pr.approval_source == "hard_floor"

    async def test_reviewer_unsure_parks(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_APPROVAL_REVIEWER", "1")

        async def unsure(**kwargs):
            return ReviewerResult(verdict=ReviewerVerdict.UNSURE, reason="ambiguous")

        set_review_fn_for_tests(unsure)
        gate = PolicyGate()
        pr = await gate.check_tool(
            user_id="u1",
            tool_name="code_execution",
            tool_args=_high_ask_args(_session_id="rev-unsure"),
        )
        assert pr.decision == PolicyDecision.APPROVAL_REQUIRED
        assert pr.hard_floor is False
        assert pr.approval_source == "reviewer_unsure"

    async def test_reviewer_deny(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_APPROVAL_REVIEWER", "1")

        async def deny(**kwargs):
            return ReviewerResult(verdict=ReviewerVerdict.DENY, reason="scope")

        set_review_fn_for_tests(deny)
        gate = PolicyGate()
        pr = await gate.check_tool(
            user_id="u1",
            tool_name="code_execution",
            tool_args=_high_ask_args(_session_id="rev-deny"),
        )
        assert pr.decision == PolicyDecision.DENY
        assert "reviewer_deny" in (pr.reason or "")
