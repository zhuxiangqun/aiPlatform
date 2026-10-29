"""HTTP contract: POST /platform/approvals/{id}/approve refuses expired requests.

Unlike core unit test_approval_expiry_gate (manager-only), this hits the
platform router and asserts the 409 `approval_expired` envelope.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_approve_expired_returns_409_via_http(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))

    from api.routers import approvals as approvals_mod
    from auth.deps import require_auth
    from core.api.core_facade import RequestStatus
    from core.services.execution_store import get_execution_store, reset_execution_store

    reset_execution_store()
    store = get_execution_store()
    await store.init()

    rid = "req_http_expired"
    now = time.time()
    await store.upsert_approval_request(
        {
            "request_id": rid,
            "user_id": "admin",
            "operation": "config:publish",
            "details": "expired http test",
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
    )

    class _Mgr:
        def __init__(self, execution_store):
            self.execution_store = execution_store

        async def get_request_async(self, request_id: str):
            row = await self.execution_store.get_approval_request(request_id)
            if not row:
                return None
            exp = row.get("expires_at")
            return SimpleNamespace(
                request_id=request_id,
                status=RequestStatus.PENDING,
                expires_at=exp,
                is_expired=lambda: True,
                metadata=row.get("metadata") or {},
            )

        async def approve(self, **kwargs):
            raise AssertionError("approve must not run for expired request")

    monkeypatch.setattr(approvals_mod, "_approval_mgr", lambda: _Mgr(store))
    monkeypatch.setattr(approvals_mod, "_store", lambda: store)

    async def _allow_rbac(**kwargs):
        return None

    monkeypatch.setattr(approvals_mod, "rbac_guard", _allow_rbac)

    app = FastAPI()
    app.dependency_overrides[require_auth] = lambda: "admin"
    app.include_router(approvals_mod.router, prefix="/api")

    with TestClient(app) as client:
        r = client.post(
            f"/api/platform/approvals/{rid}/approve",
            json={"approved_by": "admin", "comments": ""},
        )

    assert r.status_code == 409, r.text
    detail = r.json().get("detail") or {}
    if isinstance(detail, dict):
        code = detail.get("code") or (detail.get("error") or {}).get("code")
    else:
        code = None
    assert code == "approval_expired", r.text
