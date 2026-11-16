"""W7 ActionExecution 最小切片：customer_action 幂等 + before/after。"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.infrastructure import action_execution as ae


def test_require_keys_platform_passthrough():
    assert ae.require_customer_execution_keys(
        "platform_action:knowledge:confirm_extraction", {}
    ) is None


def test_require_keys_customer_missing():
    miss_tenant = ae.require_customer_execution_keys(
        "customer_action:lock-service:accept_order",
        {"idempotency_key": "k1"},
    )
    assert miss_tenant and miss_tenant["error"] == "tenant_id_required"

    miss_key = ae.require_customer_execution_keys(
        "customer_action:lock-service:accept_order",
        {"tenant_id": "t1"},
    )
    assert miss_key and miss_key["error"] == "idempotency_key_required"


def test_persist_and_lookup_idempotent(tmp_path):
    db = str(tmp_path / "exec.db")
    rec = {
        "execution_id": "exec_a",
        "tenant_id": "tenant-a",
        "idempotency_key": "idem-1",
        "action_id": "customer_action:lock-service:accept_order",
        "actor": "u1",
        "target": "order-1",
        "status": "succeeded",
        "policy_decision": "allow",
        "before_snapshot": {"status": "pending"},
        "after_snapshot": {"status": "executed"},
        "result": {"ok": True},
        "input_hash": "sha256:x",
        "started_at": 1.0,
        "completed_at": 2.0,
    }
    first = ae.persist_execution(rec, db_path=db)
    assert first["execution_id"] == "exec_a"
    assert first["before_snapshot"]["status"] == "pending"
    assert first["after_snapshot"]["status"] == "executed"
    assert first.get("audit_hash")

    second = ae.persist_execution(
        {**rec, "execution_id": "exec_b", "result": {"ok": False}},
        db_path=db,
    )
    # 为什么：重复键必须回放原记录，禁止改写
    assert second["execution_id"] == "exec_a"
    assert second["result"] == {"ok": True}

    got = ae.lookup_execution("tenant-a", "idem-1", db_path=db)
    assert got and got["execution_id"] == "exec_a"


@pytest.mark.asyncio
async def test_run_customer_missing_keys(tmp_path):
    db = str(tmp_path / "exec.db")
    out = await ae.run_customer_action_with_execution(
        action_id="customer_action:lock-service:accept_order",
        entity_ref="order-1",
        params={"tenant_id": "t1"},
        execute_fn=AsyncMock(),
        db_path=db,
    )
    assert out["status"] == "invalid"
    assert out["error"] == "idempotency_key_required"


@pytest.mark.asyncio
async def test_run_customer_idempotent_replay(tmp_path):
    db = str(tmp_path / "exec.db")
    fn = AsyncMock(
        return_value={"status": "executed", "result": {"new_state": "accepted"}}
    )
    params = {
        "tenant_id": "tenant-a",
        "idempotency_key": "idem-replay",
        "pipeline_run_id": "run-1",
        "evidence_ref": "ev-1",
    }
    first = await ae.run_customer_action_with_execution(
        action_id="customer_action:lock-service:accept_order",
        entity_ref=("lock-service", "order-1"),
        params=params,
        actor="u1",
        permissions=["action:lock-service:accept_order"],
        execute_fn=fn,
        db_path=db,
    )
    assert first["status"] == "executed"
    assert first["execution"]["before_snapshot"]
    assert first["execution"]["after_snapshot"]
    assert first["execution"]["idempotency_key"] == "idem-replay"
    assert fn.await_count == 1

    second = await ae.run_customer_action_with_execution(
        action_id="customer_action:lock-service:accept_order",
        entity_ref=("lock-service", "order-1"),
        params=params,
        actor="u1",
        permissions=["action:lock-service:accept_order"],
        execute_fn=fn,
        db_path=db,
    )
    assert second["status"] == "idempotent_replay"
    assert second["execution"]["execution_id"] == first["execution"]["execution_id"]
    assert fn.await_count == 1  # 未再次执行 handler
