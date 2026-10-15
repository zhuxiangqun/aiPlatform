"""OpenWorker-inspired P1: shell command risk + unattended approval Inbox."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.harness.infrastructure.gates.approval_gate import (
    ApprovalGate,
    ApprovalSeverity,
    ApprovalVerdict,
    get_approval_gate,
    reset_approval_gate,
)
from core.harness.infrastructure.gates.approval_inbox import (
    ATTENDED,
    AUTO,
    INBOX,
    _reset_approval_inbox,
    get_approval_inbox,
    normalize_attendance,
    park_if_unattended,
    refuse_unattended_self_approve,
)
from core.harness.infrastructure.gates.policy_gate import PolicyDecision, PolicyGate
from core.harness.infrastructure.gates.shell_command_risk import (
    analyze_shell_command,
    evaluate_tool_shell_risk,
    extract_command_text,
)


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    reset_approval_gate()
    _reset_approval_inbox()
    monkeypatch.setenv("AIPLAT_APPROVAL_INBOX_FILE", str(tmp_path / "inbox.json"))
    yield
    reset_approval_gate()
    _reset_approval_inbox()
    for k in (
        "AIPLAT_APPROVAL_GATE_DISABLED",
        "AIPLAT_HARD_FLOOR_DISABLED",
        "AIPLAT_APPROVALS_DISABLED",
    ):
        os.environ.pop(k, None)


class TestShellCommandRisk:
    def test_extract_command(self):
        assert extract_command_text({"command": "ls -la"}) == "ls -la"
        assert extract_command_text({"argv": ["echo", "hi"]}) == "echo hi"

    def test_find_exec_forces_floor(self):
        r = analyze_shell_command("find . -exec rm {} +")
        assert r.forces_hard_floor
        assert any("dangerous flag" in x for x in r.reasons)

    def test_sudo_is_arg_executor(self):
        r = analyze_shell_command("sudo apt update")
        assert r.forces_hard_floor
        assert any("arg-executor" in x for x in r.reasons)

    def test_python_dash_c_inline(self):
        r = analyze_shell_command('python3 -c "print(1)"')
        assert r.forces_hard_floor
        assert any("inline code" in x for x in r.reasons)

    def test_harmless_ls_no_escalation(self):
        r = analyze_shell_command("ls -la /tmp")
        assert not r.forces_hard_floor

    def test_opaque_substitution(self):
        r = analyze_shell_command("echo $(whoami)")
        assert r.forces_hard_floor

    def test_evaluate_tool_shell_risk_on_code_execution(self):
        report = evaluate_tool_shell_risk(
            "code_execution",
            {"code": 'python -c "import os; os.system(\'id\')"'},
        )
        assert report is not None and report.forces_hard_floor

    def test_approval_gate_escalates_code_execution_inline(self):
        gate = get_approval_gate()
        # Catalogue marks code_execution * as HIGH — shell heuristics lift to hard floor.
        result = gate.check(
            "code_execution",
            {"code": "python3 -c 'print(1)'"},
            auto_approve=True,
        )
        assert result.verdict == ApprovalVerdict.ASK
        assert result.hard_floor is True
        assert result.severity == ApprovalSeverity.CRITICAL


class TestApprovalInbox:
    def test_normalize_attendance(self):
        assert normalize_attendance(True) == INBOX
        assert normalize_attendance("auto") == AUTO
        assert normalize_attendance("weird") == ATTENDED

    def test_refuse_hard_floor_under_inbox(self):
        assert refuse_unattended_self_approve(hard_floor=True, attendance=INBOX) is True
        assert refuse_unattended_self_approve(hard_floor=True, attendance=ATTENDED) is False
        assert refuse_unattended_self_approve(
            hard_floor=True, attendance=ATTENDED, auto_approve=True,
        ) is True

    def test_park_attended_returns_none(self):
        store = get_approval_inbox()
        store.set_attendance("s1", ATTENDED)
        assert park_if_unattended(session_id="s1", title="x") is None

    def test_park_inbox_pending(self):
        store = get_approval_inbox()
        store.set_attendance("s2", INBOX)
        item = park_if_unattended(
            session_id="s2",
            title="Approve shell",
            hard_floor=True,
            tool_name="shell_exec",
            tool_call_id="c1",
        )
        assert item is not None
        assert item.state == "pending"
        assert item.visibility == "inbox"
        listed = store.list_items(visibility="inbox", pending_only=True)
        assert any(x["id"] == item.id for x in listed)
        # Idempotent re-park
        again = park_if_unattended(
            session_id="s2", title="Approve shell", tool_call_id="c1",
        )
        assert again is not None and again.id == item.id

    def test_auto_denies_hard_floor(self):
        store = get_approval_inbox()
        store.set_attendance("s3", AUTO)
        item = park_if_unattended(
            session_id="s3",
            title="Approve rm",
            hard_floor=True,
            tool_name="shell_exec",
        )
        assert item is not None
        assert item.state == "resolved"
        assert item.resolution == "deny"

    def test_resolve_first_wins(self):
        store = get_approval_inbox()
        store.set_attendance("s4", INBOX)
        item = park_if_unattended(session_id="s4", title="q")
        assert item is not None
        a = store.resolve(item.id, "allow", resolved_by="alice")
        b = store.resolve(item.id, "deny", resolved_by="bob")
        assert a is not None and a.resolution == "allow"
        assert b is not None and b.resolution == "allow"
        assert b.resolved_by == "alice"

    def test_persist_roundtrip(self, tmp_path, monkeypatch):
        path = tmp_path / "inbox2.json"
        monkeypatch.setenv("AIPLAT_APPROVAL_INBOX_FILE", str(path))
        _reset_approval_inbox()
        store = get_approval_inbox()
        store.set_attendance("persist", INBOX)
        item = park_if_unattended(session_id="persist", title="keep")
        assert item is not None
        _reset_approval_inbox()
        store2 = get_approval_inbox()
        assert store2.get_attendance("persist") == INBOX
        assert store2.get(item.id) is not None

    def test_core_facade_exports_present(self):
        # Avoid importing core_facade (heavy deps / Py3.9 union syntax on some paths).
        facade = Path(__file__).resolve().parents[3] / "api" / "core_facade.py"
        text = facade.read_text(encoding="utf-8")
        for name in (
            "list_unattended_approval_inbox",
            "resolve_unattended_approval",
            "set_unattended_attendance",
            "ApprovalInboxStore",
            "InboxItem",
        ):
            assert name in text, f"missing CoreFacade wiring for {name}"


@pytest.mark.asyncio
class TestPolicyGateInboxWiring:
    async def test_inbox_attendance_parks_and_returns_id(self):
        gate = PolicyGate()
        pr = await gate.check_tool(
            user_id="u1",
            tool_name="shell_exec",
            tool_args={
                "command": "rm -rf /",
                "_session_id": "sess-inbox",
                "_attendance": "inbox",
                "_tool_call_id": "tc-1",
            },
        )
        assert pr.decision == PolicyDecision.APPROVAL_REQUIRED
        assert pr.hard_floor is True
        assert pr.inbox_item_id
        assert pr.attendance == INBOX

    async def test_auto_attendance_denies_hard_floor(self):
        gate = PolicyGate()
        pr = await gate.check_tool(
            user_id="u1",
            tool_name="shell_exec",
            tool_args={
                "command": "sudo id",
                "_session_id": "sess-auto",
                "_attendance": "auto",
            },
        )
        assert pr.decision == PolicyDecision.DENY
        assert pr.inbox_item_id
        assert "inbox_auto_denied" in (pr.reason or "")
