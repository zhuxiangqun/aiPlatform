"""
Tests for Approval System module.

Tests cover:
- ApprovalRule matching logic
- ApprovalRequest lifecycle
- ApprovalManager CRUD operations
- Rule type evaluation
- First-time operation tracking
- Auto-approval flow
- check_and_request workflow
- Statistics
"""

import pytest
from datetime import datetime, timedelta

from harness.infrastructure.approval.types import (
    RuleType,
    RequestStatus,
    ApprovalRule,
    ApprovalRequest,
    ApprovalResult,
    ApprovalContext,
)
from harness.infrastructure.approval.manager import (
    ApprovalManager,
    ApprovalValidationError,
    create_approval_manager,
)


class TestRuleType:
    """Tests for RuleType enum."""

    def test_all_rule_types(self):
        assert RuleType.AMOUNT_THRESHOLD.value == "amount_threshold"
        assert RuleType.SENSITIVE_OPERATION.value == "sensitive_operation"
        assert RuleType.BATCH_OPERATION.value == "batch_operation"
        assert RuleType.FIRST_TIME.value == "first_time"


class TestRequestStatus:
    """Tests for RequestStatus enum."""

    def test_all_statuses(self):
        assert RequestStatus.PENDING.value == "pending"
        assert RequestStatus.APPROVED.value == "approved"
        assert RequestStatus.REJECTED.value == "rejected"
        assert RequestStatus.CANCELLED.value == "cancelled"
        assert RequestStatus.EXPIRED.value == "expired"
        assert RequestStatus.AUTO_APPROVED.value == "auto_approved"


class TestApprovalRule:
    """Tests for ApprovalRule matching logic."""

    def test_amount_threshold_match(self):
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额阈值",
            threshold=10000.0
        )
        context = ApprovalContext(
            user_id="user1",
            operation="transfer",
            amount=15000.0
        )
        assert rule.matches(context) is True

    def test_amount_threshold_no_match(self):
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额阈值",
            threshold=10000.0
        )
        context = ApprovalContext(
            user_id="user1",
            operation="transfer",
            amount=5000.0
        )
        assert rule.matches(context) is False

    def test_amount_threshold_no_amount(self):
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额阈值",
            threshold=10000.0
        )
        context = ApprovalContext(user_id="user1", operation="transfer")
        assert rule.matches(context) is False

    def test_sensitive_operation_match(self):
        rule = ApprovalRule(
            rule_id="sensitive_rule",
            rule_type=RuleType.SENSITIVE_OPERATION,
            name="敏感操作",
            metadata={"sensitive_operations": ["delete_data", "modify_permissions"]}
        )
        context = ApprovalContext(
            user_id="user1",
            operation="delete_data"
        )
        assert rule.matches(context) is True

    def test_sensitive_operation_no_match(self):
        rule = ApprovalRule(
            rule_id="sensitive_rule",
            rule_type=RuleType.SENSITIVE_OPERATION,
            name="敏感操作",
            metadata={"sensitive_operations": ["delete_data"]}
        )
        context = ApprovalContext(
            user_id="user1",
            operation="read_data"
        )
        assert rule.matches(context) is False

    def test_batch_operation_match(self):
        rule = ApprovalRule(
            rule_id="batch_rule",
            rule_type=RuleType.BATCH_OPERATION,
            name="批量操作",
            threshold=10
        )
        context = ApprovalContext(
            user_id="user1",
            operation="batch_delete",
            batch_size=50
        )
        assert rule.matches(context) is True

    def test_batch_operation_no_match(self):
        rule = ApprovalRule(
            rule_id="batch_rule",
            rule_type=RuleType.BATCH_OPERATION,
            name="批量操作",
            threshold=10
        )
        context = ApprovalContext(
            user_id="user1",
            operation="batch_delete",
            batch_size=5
        )
        assert rule.matches(context) is False

    def test_first_time_match(self):
        rule = ApprovalRule(
            rule_id="first_time_rule",
            rule_type=RuleType.FIRST_TIME,
            name="首次操作"
        )
        context = ApprovalContext(
            user_id="user1",
            operation="new_operation",
            is_first_time=True
        )
        assert rule.matches(context) is True

    def test_first_time_no_match(self):
        rule = ApprovalRule(
            rule_id="first_time_rule",
            rule_type=RuleType.FIRST_TIME,
            name="首次操作"
        )
        context = ApprovalContext(
            user_id="user1",
            operation="known_operation",
            is_first_time=False
        )
        assert rule.matches(context) is False

    def test_disabled_rule_no_match(self):
        rule = ApprovalRule(
            rule_id="disabled_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="禁用规则",
            threshold=100.0,
            enabled=False
        )
        context = ApprovalContext(user_id="user1", operation="transfer", amount=500.0)
        assert rule.matches(context) is False


class TestApprovalRequest:
    """Tests for ApprovalRequest."""

    def test_default_request(self):
        request = ApprovalRequest(
            request_id="req-1",
            user_id="user1",
            operation="transfer"
        )
        assert request.status == RequestStatus.PENDING
        assert request.is_resolved() is False

    def test_is_expired(self):
        request = ApprovalRequest(
            request_id="req-1",
            user_id="user1",
            operation="transfer",
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        assert request.is_expired() is True

    def test_is_not_expired(self):
        request = ApprovalRequest(
            request_id="req-1",
            user_id="user1",
            operation="transfer",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        assert request.is_expired() is False

    def test_no_expiration(self):
        request = ApprovalRequest(
            request_id="req-1",
            user_id="user1",
            operation="transfer"
        )
        assert request.is_expired() is False

    def test_is_resolved_approved(self):
        request = ApprovalRequest(
            request_id="req-1",
            user_id="user1",
            operation="transfer",
            status=RequestStatus.APPROVED
        )
        assert request.is_resolved() is True

    def test_is_resolved_rejected(self):
        request = ApprovalRequest(
            request_id="req-1",
            user_id="user1",
            operation="transfer",
            status=RequestStatus.REJECTED
        )
        assert request.is_resolved() is True

    def test_is_resolved_pending(self):
        request = ApprovalRequest(
            request_id="req-1",
            user_id="user1",
            operation="transfer",
            status=RequestStatus.PENDING
        )
        assert request.is_resolved() is False


class TestApprovalManager:
    """Tests for ApprovalManager."""

    def test_register_rule(self):
        manager = ApprovalManager()
        rule = ApprovalRule(
            rule_id="rule1",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        )
        rule_id = manager.register_rule(rule)
        assert rule_id == "rule1"
        assert manager.get_rule("rule1") is not None

    def test_unregister_rule(self):
        manager = ApprovalManager()
        rule = ApprovalRule(
            rule_id="rule1",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        )
        manager.register_rule(rule)
        result = manager.unregister_rule("rule1")
        assert result is True
        assert manager.get_rule("rule1") is None

    def test_check_approval_required_matching(self):
        manager = ApprovalManager()
        manager.register_rule(ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0,
            priority=10
        ))
        context = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        matched = manager.check_approval_required(context)
        assert matched is not None
        assert matched.rule_id == "amount_rule"

    def test_check_approval_required_no_match(self):
        manager = ApprovalManager()
        manager.register_rule(ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        ))
        context = ApprovalContext(user_id="user1", operation="transfer", amount=5000.0)
        matched = manager.check_approval_required(context)
        assert matched is None

    def test_create_request_auto_approve(self):
        manager = ApprovalManager()
        context = ApprovalContext(user_id="user1", operation="small_transfer", amount=100.0)
        request = manager.create_request(context, rule=None)
        assert request.status == RequestStatus.AUTO_APPROVED

    def test_create_request_needs_approval(self):
        manager = ApprovalManager()
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        )
        context = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        request = manager.create_request(context, rule=rule)
        assert request.status == RequestStatus.PENDING
        assert request.rule_id == "amount_rule"

    @pytest.mark.asyncio
    async def test_approve_request(self):
        manager = ApprovalManager()
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        )
        context = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        request = manager.create_request(context, rule=rule)
        
        result = await manager.approve(request.request_id, "admin", "看起来没问题")
        assert result is not None
        assert result.status == RequestStatus.APPROVED
        assert result.result.approved_by == "admin"

    @pytest.mark.asyncio
    async def test_reject_request(self):
        manager = ApprovalManager()
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        )
        context = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        request = manager.create_request(context, rule=rule)
        
        result = await manager.reject(request.request_id, "admin", "金额过大")
        assert result is not None
        assert result.status == RequestStatus.REJECTED

    def test_get_pending_requests(self):
        manager = ApprovalManager()
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        )
        context1 = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        context2 = ApprovalContext(user_id="user2", operation="transfer", amount=20000.0)
        manager.create_request(context1, rule=rule)
        manager.create_request(context2, rule=rule)
        
        pending = manager.get_pending_requests()
        assert len(pending) == 2

    def test_auto_approve(self):
        manager = ApprovalManager()
        rule = ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        )
        context = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        request = manager.create_request(context, rule=rule)
        
        auto_approved = manager.auto_approve(request.request_id, "系统自动审批")
        assert auto_approved is not None
        assert auto_approved.status == RequestStatus.AUTO_APPROVED

    def test_check_and_request_no_rules(self):
        manager = ApprovalManager()
        context = ApprovalContext(user_id="user1", operation="transfer", amount=100.0)
        request = manager.check_and_request(context)
        assert request.status == RequestStatus.AUTO_APPROVED

    def test_check_and_request_needs_approval(self):
        manager = ApprovalManager()
        manager.register_rule(ApprovalRule(
            rule_id="amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额规则",
            threshold=10000.0
        ))
        context = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        request = manager.check_and_request(context)
        assert request.status == RequestStatus.PENDING

    def test_check_and_request_auto_approve_rule(self):
        manager = ApprovalManager()
        manager.register_rule(ApprovalRule(
            rule_id="low_amount_rule",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="低金额自动审批",
            threshold=100.0,
            auto_approve=True
        ))
        context = ApprovalContext(user_id="user1", operation="transfer", amount=5000.0)
        request = manager.check_and_request(context)
        assert request.status == RequestStatus.AUTO_APPROVED

    def test_first_time_tracking(self):
        manager = ApprovalManager()
        manager.register_rule(ApprovalRule(
            rule_id="first_time_rule",
            rule_type=RuleType.FIRST_TIME,
            name="首次操作",
            auto_approve=False
        ))
        
        context1 = ApprovalContext(user_id="user1", operation="new_op", is_first_time=True)
        request1 = manager.check_and_request(context1)
        assert request1.status == RequestStatus.PENDING

    def test_list_rules(self):
        manager = ApprovalManager()
        manager.register_rule(ApprovalRule(
            rule_id="rule1",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="Rule 1",
            priority=10
        ))
        manager.register_rule(ApprovalRule(
            rule_id="rule2",
            rule_type=RuleType.SENSITIVE_OPERATION,
            name="Rule 2",
            priority=5
        ))
        
        all_rules = manager.list_rules()
        assert len(all_rules) == 2
        
        amount_rules = manager.list_rules(rule_type=RuleType.AMOUNT_THRESHOLD)
        assert len(amount_rules) == 1
        
        enabled_rules = manager.list_rules(enabled_only=True)
        assert len(enabled_rules) == 2

    def test_get_stats(self):
        manager = ApprovalManager()
        manager.register_rule(ApprovalRule(
            rule_id="rule1",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="Rule 1",
            threshold=10000.0
        ))
        
        context = ApprovalContext(user_id="user1", operation="transfer", amount=15000.0)
        manager.create_request(context, rule=manager.get_rule("rule1"))
        
        stats = manager.get_stats()
        assert stats["total_requests"] == 1
        assert stats["active_rules"] == 1
        assert stats["total_rules"] == 1


class TestCreateApprovalManager:
    """Tests for create_approval_manager factory."""

    def test_create_without_defaults(self):
        manager = create_approval_manager(default_rules=False)
        rules = manager.list_rules()
        assert len(rules) == 0

    def test_create_with_defaults(self):
        manager = create_approval_manager(default_rules=True)
        rules = manager.list_rules()
        assert len(rules) == 4
        
        rule_types = {r.rule_type for r in rules}
        assert RuleType.AMOUNT_THRESHOLD in rule_types
        assert RuleType.SENSITIVE_OPERATION in rule_types
        assert RuleType.BATCH_OPERATION in rule_types
        assert RuleType.FIRST_TIME in rule_types

    def test_default_amount_threshold(self):
        manager = create_approval_manager(default_rules=True)
        amount_rule = manager.get_rule("default_amount_threshold")
        assert amount_rule is not None
        assert amount_rule.threshold == 10000.0