"""OpenWorker-inspired P0 governance: hard floors, RiskClass, approval provenance."""
from __future__ import annotations

import os

import pytest

from core.harness.infrastructure.gates.approval_gate import (
    APPROVAL_SOURCE_AUTO,
    APPROVAL_SOURCE_HARD_FLOOR,
    ApprovalGate,
    ApprovalSeverity,
    ApprovalVerdict,
    build_approval_provenance,
    get_approval_gate,
    reset_approval_gate,
)
from core.harness.infrastructure.gates.policy_gate import PolicyDecision, PolicyGate
from core.harness.infrastructure.gates.risk_class import (
    RiskClass,
    classify,
    register_risk,
    strictness,
)


@pytest.fixture(autouse=True)
def _reset_gate():
    reset_approval_gate()
    yield
    reset_approval_gate()
    os.environ.pop("AIPLAT_APPROVAL_GATE_DISABLED", None)
    os.environ.pop("AIPLAT_HARD_FLOOR_DISABLED", None)
    os.environ.pop("AIPLAT_APPROVALS_DISABLED", None)


class TestRiskClass:
    def test_builtin_shell_is_exec(self):
        assert classify("shell_exec") == RiskClass.EXEC

    def test_http_is_egress(self):
        assert classify("http") == RiskClass.EGRESS

    def test_slack_is_external(self):
        assert classify("slack") == RiskClass.EXTERNAL

    def test_unknown_defaults_read(self):
        assert classify("harmless_list_tool") == RiskClass.READ

    def test_requires_approval_metadata_lifts_read_to_external(self):
        assert classify("custom_send", metadata={"requires_approval": True}) == RiskClass.EXTERNAL

    def test_override_cannot_relax(self):
        assert (
            classify(
                "shell_exec",
                overrides=lambda _n: RiskClass.READ,
            )
            == RiskClass.EXEC
        )

    def test_override_can_tighten(self):
        assert (
            classify(
                "http",
                overrides=lambda _n: RiskClass.EXTERNAL,
            )
            == RiskClass.EXTERNAL
        )

    def test_register_risk_rejects_relax(self):
        with pytest.raises(ValueError, match="cannot relax"):
            register_risk("shell_exec", RiskClass.READ)

    def test_strictness_order(self):
        assert strictness(RiskClass.READ) < strictness(RiskClass.EGRESS)
        assert strictness(RiskClass.EGRESS) < strictness(RiskClass.EXTERNAL)
        assert strictness(RiskClass.WRITE_LOCAL) == strictness(RiskClass.EXEC)


class TestHardFloors:
    def test_critical_delete_is_hard_floor(self):
        gate = ApprovalGate()
        r = gate.check(
            "file_operations",
            {"operation": "delete", "path": "/tmp/x"},
            auto_approve=True,
        )
        assert r.verdict == ApprovalVerdict.ASK
        assert r.hard_floor is True
        assert r.approval_source == APPROVAL_SOURCE_HARD_FLOOR

    def test_auto_approve_cannot_waive_shell_exec(self):
        gate = ApprovalGate()
        r = gate.check("shell_exec", {"command": "ls"}, auto_approve=True)
        assert r.verdict == ApprovalVerdict.ASK
        assert r.hard_floor is True

    def test_soft_disable_still_asks_hard_floor(self):
        os.environ["AIPLAT_APPROVAL_GATE_DISABLED"] = "true"
        reset_approval_gate()
        gate = get_approval_gate()
        r = gate.check(
            "file_operations",
            {"operation": "delete", "path": "/tmp/x"},
        )
        assert r.verdict == ApprovalVerdict.ASK
        assert r.hard_floor is True

    def test_session_approve_refused_for_hard_floor(self):
        gate = ApprovalGate()
        r = gate.check(
            "file_operations",
            {"operation": "delete", "path": "/tmp/x"},
            session_id="s1",
        )
        assert r.rule_id
        assert gate.approve_session_rule("s1", r.rule_id) is False
        r2 = gate.check(
            "file_operations",
            {"operation": "delete", "path": "/tmp/x"},
            session_id="s1",
            auto_approve=True,
        )
        assert r2.verdict == ApprovalVerdict.ASK
        assert r2.hard_floor is True

    def test_auto_approve_waives_medium_only(self):
        gate = ApprovalGate()
        r = gate.check(
            "http",
            {"url": "http://example.com", "method": "GET"},
            auto_approve=True,
        )
        assert r.verdict == ApprovalVerdict.ALLOW
        assert r.approval_source == APPROVAL_SOURCE_AUTO
        assert r.hard_floor is False

    def test_hard_floor_escape_hatch(self):
        os.environ["AIPLAT_HARD_FLOOR_DISABLED"] = "true"
        os.environ["AIPLAT_APPROVAL_GATE_DISABLED"] = "true"
        reset_approval_gate()
        gate = get_approval_gate()
        r = gate.check(
            "file_operations",
            {"operation": "delete", "path": "/tmp/x"},
        )
        assert r.verdict == ApprovalVerdict.ALLOW


class TestProvenanceHelper:
    def test_build_approval_provenance_shape(self):
        p = build_approval_provenance(
            source=APPROVAL_SOURCE_HARD_FLOOR,
            rule_id="danger_000",
            severity=ApprovalSeverity.CRITICAL.value,
            hard_floor=True,
            risk_class=RiskClass.WRITE_LOCAL.value,
            reason="delete",
        )
        assert p["source"] == APPROVAL_SOURCE_HARD_FLOOR
        assert p["hard_floor"] is True
        assert p["risk_class"] == "write_local"
        assert p["rule_id"] == "danger_000"


@pytest.mark.asyncio
class TestPolicyGateHardFloorWiring:
    async def test_disable_approvals_still_blocks_hard_floor(self):
        """OpenWorker parity: AIPLAT_APPROVALS_DISABLED must not lower hard floors."""
        gate = PolicyGate()
        gate._disable_approvals = True
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="file_operations",
            tool_args={"operation": "delete", "path": "/tmp/x", "_session_id": "s1"},
        )
        assert result.decision == PolicyDecision.APPROVAL_REQUIRED
        assert result.hard_floor is True
        assert result.approval_source == APPROVAL_SOURCE_HARD_FLOOR
        assert result.risk_class == RiskClass.WRITE_LOCAL.value

    async def test_shell_exec_surfaces_risk_class(self):
        gate = PolicyGate()
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="shell_exec",
            tool_args={"command": "echo hi", "_session_id": "s2"},
        )
        assert result.decision == PolicyDecision.APPROVAL_REQUIRED
        assert result.risk_class == RiskClass.EXEC.value
        assert result.hard_floor is True

    async def test_auto_approve_arg_cannot_waive_critical(self):
        gate = PolicyGate()
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="shell_exec",
            tool_args={
                "command": "ls",
                "_session_id": "s3",
                "_auto_approve": True,
            },
        )
        assert result.decision == PolicyDecision.APPROVAL_REQUIRED
        assert result.hard_floor is True
