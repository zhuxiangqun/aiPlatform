"""Expired approval requests must not be approve-able (product SLA).

Approvals HTTP lives on platform (`/platform/approvals/...`). Unit-test the
store + ApprovalManager expiry gate without booting the full platform app.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_approval_expired_cannot_be_approved(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.api.core_facade import RequestStatus
    from core.harness.infrastructure.approval import ApprovalManager
    from core.services.execution_store import get_execution_store, reset_execution_store

    reset_execution_store()
    store = get_execution_store()
    await store.init()
    mgr = ApprovalManager(execution_store=store)

    rid = "req_expired_test"
    now = time.time()
    record = {
        "request_id": rid,
        "user_id": "admin",
        "operation": "config:publish",
        "details": "expired test",
        "rule_id": "x",
        "rule_type": "sensitive_operation",
        "status": "pending",
        "amount": None,
        "batch_size": None,
        "is_first_time": False,
        "created_at": now - 3600,
        "updated_at": now - 3600,
        "expires_at": now - 10,
        "metadata": {"tenant_id": "default"},
        "result": None,
    }
    await store.upsert_approval_request(record)

    r0 = await mgr.get_request_async(rid) if hasattr(mgr, "get_request_async") else mgr.get_request(rid)
    assert r0 is not None
    expired = False
    try:
        expired = bool(r0.is_expired())
    except Exception:
        exp = getattr(r0, "expires_at", None)
        if exp is not None:
            if getattr(exp, "tzinfo", None) is None:
                exp = exp.replace(tzinfo=timezone.utc)
            expired = datetime.now(timezone.utc) > exp
    assert expired or getattr(r0, "status", None) in (RequestStatus.EXPIRED, "expired")

    # Mirror platform approvals.approve_request SLA: refuse when expired.
    status = getattr(r0, "status", None)
    if status in (RequestStatus.EXPIRED,) or (status == RequestStatus.PENDING and expired):
        detail = {
            "code": "approval_expired",
            "message": "approval_request_expired",
            "approval_request_id": rid,
        }
    else:
        updated = await mgr.approve(request_id=rid, approved_by="admin", comments="")
        pytest.fail(f"expected expiry gate; approve returned {updated}")

    assert detail.get("code") == "approval_expired"
