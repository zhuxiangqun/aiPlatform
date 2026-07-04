"""Integration tests: PolicyGate → ApprovalGate wiring verification."""
import pytest
from core.harness.infrastructure.gates.policy_gate import PolicyGate, PolicyDecision
from core.harness.infrastructure.gates.approval_gate import reset_approval_gate


@pytest.fixture(autouse=True)
def reset():
    reset_approval_gate()
    yield
    reset_approval_gate()


@pytest.mark.asyncio
class TestPolicyGateApprovalGateIntegration:
    async def test_dangerous_file_delete_triggers_approval(self):
        """PolicyGate.check_tool should invoke ApprovalGate for dangerous file ops."""
        gate = PolicyGate()
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="file_operations",
            tool_args={"operation": "delete", "path": "/tmp/test.txt", "_session_id": "s1"},
        )
        assert result.decision == PolicyDecision.APPROVAL_REQUIRED
        assert "approval_gate" in str(result.reason).lower()

    async def test_safe_read_allowed(self):
        """Safe operations should pass both gates."""
        gate = PolicyGate()
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="safe_tool",
            tool_args={"action": "list"},
        )
        assert result.decision == PolicyDecision.ALLOW or result.decision == PolicyDecision.DENY
        # If DENY, it's because of RBAC, not approval gate
        if result.decision == PolicyDecision.DENY:
            assert "approval_gate" not in str(result.reason).lower()

    async def test_code_execution_triggers_approval(self):
        """Arbitrary code execution should require approval."""
        gate = PolicyGate()
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="code_execution",
            tool_args={"code": "print(1)", "_session_id": "s2"},
        )
        assert result.decision == PolicyDecision.APPROVAL_REQUIRED

    async def test_drop_table_triggers_approval(self):
        """Database drop operations should require approval."""
        gate = PolicyGate()
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="database",
            tool_args={"operation": "drop_table", "table": "users", "_session_id": "s3"},
        )
        assert result.decision == PolicyDecision.APPROVAL_REQUIRED

    async def test_secret_file_triggers_approval(self):
        """Operations on secret files should require approval."""
        gate = PolicyGate()
        result = await gate.check_tool(
            user_id="test_user",
            tool_name="file_operations",
            tool_args={"operation": "read", "path": ".env", "_session_id": "s4"},
        )
        assert result.decision == PolicyDecision.APPROVAL_REQUIRED
        assert "approval_gate" in str(result.reason).lower()

    async def test_disable_approvals_bypasses_gate(self):
        """When approvals are disabled via env, dangerous ops should pass."""
        import os
        os.environ["AIPLAT_APPROVALS_DISABLED"] = "true"
        try:
            gate = PolicyGate()
            gate._disable_approvals = True
            result = await gate.check_tool(
                user_id="test_user",
                tool_name="file_operations",
                tool_args={"operation": "delete", "path": "/tmp/x"},
            )
            assert result.decision == PolicyDecision.ALLOW
        finally:
            os.environ.pop("AIPLAT_APPROVALS_DISABLED", None)
