"""Tests for action_audit_validate + FDE register-time namespace checks."""

from __future__ import annotations

import pytest

from core.harness.infrastructure.action_audit_validate import (
    ActionNamespace,
    build_audit_record,
    hash_params,
    map_audit_to_action_store,
    validate_action_contract,
)
from core.harness.infrastructure.action_contract import ActionContractModel, RiskLevel
from core.harness.ontology_engine.action_registry import AsyncActionRegistry


def test_validate_customer_high_risk_requires_hitl():
    with pytest.raises(ValueError, match="require_approval"):
        validate_action_contract(
            action_id="customer_action:lock-service:accept_order",
            action_namespace=ActionNamespace.CUSTOMER.value,
            domain_id="lock-service",
            eval_gate="customer_action_safety",
            risk_level="high",
            require_approval=False,
        )


def test_validate_rejects_platform_domain_for_customer():
    with pytest.raises(ValueError, match="不得使用平台跟踪域"):
        validate_action_contract(
            action_id="customer_action:fde-delivery:foo",
            action_namespace=ActionNamespace.CUSTOMER.value,
            domain_id="fde-delivery",
            eval_gate="customer_action_safety",
            risk_level="medium",
            require_approval=True,
        )


def test_validate_requires_known_eval_gate():
    with pytest.raises(ValueError, match="未在 audit_schema"):
        validate_action_contract(
            action_id="customer_action:lock-service:accept_order",
            action_namespace=ActionNamespace.CUSTOMER.value,
            domain_id="lock-service",
            eval_gate="not_a_real_gate",
            risk_level="medium",
            require_approval=True,
        )


def test_legacy_empty_namespace_skipped():
    validate_action_contract(
        action_id="accept_order",
        action_namespace="",
        domain_id="lock-service",
    )


def test_registry_register_enforces_namespace():
    reg = AsyncActionRegistry()
    with pytest.raises(ValueError, match="require_approval"):
        reg.register(
            ActionContractModel(
                action_id="customer_action:lock-service:accept_order",
                label="Accept",
                domain_id="lock-service",
                target_class="InstallOrder",
                action_namespace="customer_action",
                eval_gate="customer_action_safety",
                risk_level=RiskLevel.HIGH,
                require_approval=False,
            )
        )


def test_build_audit_record_and_store_map():
    rec = build_audit_record(
        audit_id="aud_test",
        timestamp="2026-09-14T10:00:00+08:00",
        actor_type="agent",
        actor_id="fda-1",
        action_namespace="customer_action",
        action_name="customer_action:lock-service:accept_order",
        domain_id="lock-service",
        target_entity_type="InstallOrder",
        target_entity_id="IO-1",
        params={"order_id": "IO-1"},
        before_state_snapshot={"status": "pending"},
        after_state_snapshot={"status": "accepted"},
        result_status="success",
        policy_gate_decision={"gate_id": "g1", "decision": "allow", "reason": "ok"},
        approver_id="fde-1",
    )
    assert rec["input_params_hash"].startswith("sha256:")
    assert hash_params({"order_id": "IO-1"}) == rec["input_params_hash"]
    mapped = map_audit_to_action_store(rec)
    assert mapped["entity_snapshot"]["before"]["status"] == "pending"
    assert mapped["params"]["schema"] == "audit.v1"
