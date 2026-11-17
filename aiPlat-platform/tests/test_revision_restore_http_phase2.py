"""N24 Batch J1 — Revision Restore HTTP 薄路由（非管理端回滚 UI / 非 certified）。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """无 API key 的本地开发路径；挂载 revision_restore 子路由。"""
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)
    from apps.fde.api.revision_restore_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api/platform/apps/fde")
    return TestClient(app, raise_server_exceptions=False)


def test_list_requests_delegates_to_facade(client, monkeypatch):
    """GET requests 经 Facade 返回列表。"""

    async def _fake(**kwargs):
        assert kwargs["tenant_id"] == "t1"
        return [{"request_id": "r1", "status": "pending"}]

    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_list_revision_restore_requests",
        _fake,
    )
    r = client.get(
        "/api/platform/apps/fde/revision-restore/requests",
        params={"tenant_id": "t1"},
    )
    assert r.status_code == 200
    assert r.json()["requests"][0]["request_id"] == "r1"


def test_request_approve_reject_and_bridges(client, monkeypatch):
    """POST request/approve/reject + GET bridges 接线。"""

    async def _req(**kwargs):
        return {"request_id": "rr-1", "status": "pending", **kwargs}

    async def _approve(**kwargs):
        return {"request_id": kwargs["request_id"], "status": "approved"}

    async def _reject(**kwargs):
        return {"request_id": kwargs["request_id"], "status": "rejected"}

    async def _bridges(**kwargs):
        assert kwargs["tenant_id"] == "t1"
        return [{"bridge_id": "b1"}]

    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_request_revision_restore", _req
    )
    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_approve_revision_restore", _approve
    )
    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_reject_revision_restore", _reject
    )
    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_list_revision_action_bridges",
        _bridges,
    )

    created = client.post(
        "/api/platform/apps/fde/revision-restore/requests",
        params={"tenant_id": "t1"},
        json={
            "entity_type": "fact",
            "entity_id": "f1",
            "target_revision": 1,
            "requester": "alice",
            "reason": "rollback",
        },
    )
    assert created.status_code == 200
    assert created.json()["status"] == "pending"

    ok = client.post(
        "/api/platform/apps/fde/revision-restore/requests/rr-1/approve",
        params={"tenant_id": "t1"},
        json={"actor": "bob", "reason": "ok"},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"

    no = client.post(
        "/api/platform/apps/fde/revision-restore/requests/rr-2/reject",
        params={"tenant_id": "t1"},
        json={"actor": "bob", "reason": "no"},
    )
    assert no.status_code == 200
    assert no.json()["status"] == "rejected"

    bridges = client.get(
        "/api/platform/apps/fde/revision-restore/action-bridges",
        params={"tenant_id": "t1"},
    )
    assert bridges.status_code == 200
    assert bridges.json()["bridges"][0]["bridge_id"] == "b1"


def test_ledger_error_maps_to_400(client, monkeypatch):
    """账本 ValueError → HTTP 400。"""

    async def _boom(**kwargs):
        raise ValueError("self-approve forbidden")

    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_approve_revision_restore", _boom
    )
    r = client.post(
        "/api/platform/apps/fde/revision-restore/requests/rr-x/approve",
        params={"tenant_id": "t1"},
        json={"actor": "alice", "reason": "x"},
    )
    assert r.status_code == 400
    assert "self-approve" in r.json()["detail"]


def test_audit_and_suite_delegate(client, monkeypatch):
    """GET audit + POST suite 经 Facade。"""

    async def _audit(**kwargs):
        assert kwargs["tenant_id"] == "t1"
        return [{"event_type": "restore_approve"}]

    async def _suite(**kwargs):
        return {
            "ok": True,
            "certified": False,
            "n24_full_conformance": False,
            "tenant_id": kwargs["tenant_id"],
        }

    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_list_revision_audit", _audit
    )
    monkeypatch.setattr(
        "core.api.core_facade.fact_ledger_run_restore_approval_suite", _suite
    )

    audit = client.get(
        "/api/platform/apps/fde/revision-restore/audit",
        params={"tenant_id": "t1"},
    )
    assert audit.status_code == 200
    assert audit.json()["events"][0]["event_type"] == "restore_approve"

    suite = client.post(
        "/api/platform/apps/fde/revision-restore/suite",
        params={"tenant_id": "t-suite"},
    )
    assert suite.status_code == 200
    body = suite.json()
    assert body["certified"] is False
    assert body["n24_full_conformance"] is False


def test_gate_honesty_certified_false(client, monkeypatch):
    """门槛门 certified 恒 false。"""

    def _gate(suite=None):
        return {
            "ok": True,
            "certified": False,
            "n24_full_conformance": False,
            "suite": suite,
        }

    monkeypatch.setattr(
        "core.api.core_facade.evaluate_fact_restore_approval_gate", _gate
    )
    r = client.post(
        "/api/platform/apps/fde/revision-restore/gate",
        json={"suite": {"ok": True}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["certified"] is False
    assert body["n24_full_conformance"] is False
