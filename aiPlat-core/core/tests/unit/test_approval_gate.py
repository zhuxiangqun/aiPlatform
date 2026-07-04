"""Tests for approval_gate.py — dangerous command detection and approval enforcement."""
import pytest
from core.harness.infrastructure.gates.approval_gate import (
    ApprovalGate, ApprovalVerdict, ApprovalSeverity, ApprovalRule,
    get_approval_gate, reset_approval_gate,
)


@pytest.fixture(autouse=True)
def reset():
    reset_approval_gate()
    yield
    reset_approval_gate()


class TestApprovalGate:
    def test_safe_operation_allowed(self):
        gate = get_approval_gate()
        result = gate.check("safe_read_tool", {"action": "list", "target": "items"})
        assert result.verdict == ApprovalVerdict.ALLOW

    def test_delete_file_requires_approval(self):
        gate = get_approval_gate()
        result = gate.check("file_operations", {"operation": "delete", "path": "/tmp/test.txt"})
        assert result.verdict == ApprovalVerdict.ASK
        assert result.severity == ApprovalSeverity.CRITICAL

    def test_system_path_high(self):
        gate = get_approval_gate()
        result = gate.check("file_operations", {"operation": "read", "path": "/etc/hosts"})
        assert result.verdict == ApprovalVerdict.ASK
        assert result.severity == ApprovalSeverity.HIGH

    def test_env_file_critical(self):
        gate = get_approval_gate()
        result = gate.check("file_operations", {"operation": "read", "path": ".env"})
        assert result.verdict == ApprovalVerdict.ASK
        assert result.severity == ApprovalSeverity.CRITICAL

    def test_code_execution_high(self):
        gate = get_approval_gate()
        result = gate.check("code_execution", {"code": "print(1)"})
        assert result.verdict == ApprovalVerdict.ASK
        assert result.severity == ApprovalSeverity.HIGH

    def test_shell_exec_critical(self):
        gate = get_approval_gate()
        result = gate.check("shell_exec", {"cmd": "ls"})
        assert result.verdict == ApprovalVerdict.ASK
        assert result.severity == ApprovalSeverity.CRITICAL

    def test_destructive_command_critical(self):
        gate = get_approval_gate()
        result = gate.check("code_execution", {"code": "rm -rf /tmp/test"})
        assert result.verdict == ApprovalVerdict.ASK
        assert result.severity == ApprovalSeverity.CRITICAL

    def test_drop_table_critical(self):
        gate = get_approval_gate()
        result = gate.check("database", {"operation": "drop_table", "table": "users"})
        assert result.verdict == ApprovalVerdict.ASK

    def test_force_push_critical(self):
        gate = get_approval_gate()
        result = gate.check("repo", {"operation": "force_push"})
        assert result.verdict == ApprovalVerdict.ASK

    def test_kill_process_high(self):
        gate = get_approval_gate()
        result = gate.check("process", {"operation": "kill", "pid": 1234})
        assert result.verdict == ApprovalVerdict.ASK

    def test_sudo_command_critical(self):
        gate = get_approval_gate()
        result = gate.check("code_execution", {"code": "sudo systemctl restart nginx"})
        assert result.verdict == ApprovalVerdict.ASK

    def test_whitelist_user_low(self):
        gate = get_approval_gate()
        gate._user_whitelist.add("admin")
        result = gate.check("any_tool", {"max_files": 10}, user_id="admin")
        assert result.verdict == ApprovalVerdict.ALLOW

    def test_session_approval_cached(self):
        gate = get_approval_gate()
        med_rules = [r for r in gate._rules if r.severity == ApprovalSeverity.MEDIUM]
        if med_rules:
            rule_id = med_rules[0].rule_id
            gate.approve_session_rule("s1", rule_id)
            result = gate.check("http", {"method": "DELETE"}, session_id="s1")
            assert result.verdict == ApprovalVerdict.ALLOW

    def test_disable_gate(self):
        gate = ApprovalGate()
        gate._disabled = True
        result = gate.check("file_operations", {"operation": "delete", "path": "/"})
        assert result.verdict == ApprovalVerdict.ALLOW

    def test_add_custom_rule(self):
        gate = get_approval_gate()
        gate.add_rule(ApprovalRule(
            rule_id="custom_001",
            tool_name="custom_tool",
            arg_patterns={"action": "destroy"},
            severity=ApprovalSeverity.CRITICAL,
            message="test",
        ))
        result = gate.check("custom_tool", {"action": "destroy"})
        assert result.verdict == ApprovalVerdict.ASK
        assert result.rule_id == "custom_001"

    def test_list_rules(self):
        gate = get_approval_gate()
        rules = gate.list_rules()
        assert len(rules) > 0

    def test_get_stats(self):
        gate = get_approval_gate()
        stats = gate.get_stats()
        assert stats["total_rules"] > 0

    def test_non_https_is_medium(self):
        gate = get_approval_gate()
        result = gate.check("http", {"url": "http://example.com"})
        assert result.verdict == ApprovalVerdict.ASK  # MEDIUM → ASK

    def test_agent_delete_high(self):
        gate = get_approval_gate()
        result = gate.check("agent_manager", {"operation": "delete"})
        assert result.verdict == ApprovalVerdict.ASK

    def test_stateless_no_session(self):
        gate = get_approval_gate()
        gate.approve_session_rule("other_session", "danger_003")
        result = gate.check("database", {"operation": "drop_table", "table": "x"})
        assert result.verdict == ApprovalVerdict.ASK


class TestApprovalGateSingleton:
    def test_singleton(self):
        reset_approval_gate()
        g1 = get_approval_gate()
        g2 = get_approval_gate()
        assert g1 is g2

    def test_reset(self):
        g1 = get_approval_gate()
        reset_approval_gate()
        g2 = get_approval_gate()
        assert g1 is not g2
