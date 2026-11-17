"""N24 Batch J3 — Unified Audit View HTTP 薄路由（非全量写总线 / 非 certified）。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """无 API key 的本地开发路径；挂载 unified_audit 子路由。"""
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)
    from apps.fde.api.unified_audit_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api/platform/apps/fde")
    return TestClient(app, raise_server_exceptions=False)


def test_list_delegates_to_facade(client, monkeypatch):
    """GET unified-audit 经 Facade 返回汇合事件。"""

    async def _fake(**kwargs):
        assert kwargs["tenant_id"] == "t1"
        return {
            "events": [{"stream": "package", "event_id": "e1"}],
            "count": 1,
            "streams": ["package"],
            "certified": False,
            "n24_full_conformance": False,
        }

    monkeypatch.setattr(
        "core.api.core_facade.list_fact_unified_audit_events",
        _fake,
    )
    r = client.get(
        "/api/platform/apps/fde/unified-audit",
        params={"tenant_id": "t1", "streams": "package"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["certified"] is False


def test_value_error_maps_to_400(client, monkeypatch):
    """缺租户等 ValueError → HTTP 400。"""

    async def _boom(**kwargs):
        raise ValueError("tenant_id required")

    monkeypatch.setattr(
        "core.api.core_facade.list_fact_unified_audit_events",
        _boom,
    )
    r = client.get("/api/platform/apps/fde/unified-audit", params={"tenant_id": "x"})
    assert r.status_code == 400


def test_suite_and_gate_honesty(client, monkeypatch):
    """suite/gate 透传；gate certified 恒 false。"""

    async def _suite(**kwargs):
        return {
            "suite": "unified_audit_view",
            "ok": True,
            "passed": 4,
            "total": 4,
            "certified": False,
            "n24_full_conformance": False,
        }

    def _gate(*, suite=None):
        return {
            "gate": "unified_audit_view",
            "ok": True,
            "certified": False,
            "n24_full_conformance": False,
            "issues": [],
        }

    monkeypatch.setattr(
        "core.api.core_facade.run_fact_unified_audit_view_suite", _suite
    )
    monkeypatch.setattr(
        "core.api.core_facade.evaluate_fact_unified_audit_view_gate", _gate
    )
    s = client.post("/api/platform/apps/fde/unified-audit/suite")
    assert s.status_code == 200
    assert s.json()["certified"] is False
    g = client.post("/api/platform/apps/fde/unified-audit/gate", json={})
    assert g.status_code == 200
    assert g.json()["certified"] is False
