"""
Tests for Infrastructure API endpoints (management -> infra forwarding).

These tests validate that aiPlat-management routes can forward to aiPlat-infra API
without requiring a real network service, using ASGITransport.
"""

import pytest
import httpx
from fastapi.testclient import TestClient

from management.server import create_app
from management.infra_client import InfraAPIClient, InfraAPIClientConfig


@pytest.fixture
def client():
    app = create_app()
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/api/infra/status":
            return httpx.Response(200, json={"status": "success", "data": {"node": "healthy"}})
        if p == "/api/infra/health":
            return httpx.Response(200, json={"status": "success", "data": {"node": {"status": "healthy"}}})
        if p == "/api/infra/metrics":
            return httpx.Response(200, json={"status": "success", "data": {"node": []}})
        if p == "/api/infra/nodes":
            return httpx.Response(200, json=[])
        if p == "/api/infra/services":
            return httpx.Response(200, json=[])
        if p == "/api/infra/scheduler/quotas":
            return httpx.Response(200, json=[])
        if p == "/api/infra/scheduler/tasks":
            return httpx.Response(200, json=[])
        if p == "/api/infra/storage/pvcs":
            return httpx.Response(200, json=[])
        if p == "/api/infra/storage/collections":
            return httpx.Response(200, json=[])
        if p == "/api/infra/network/services":
            return httpx.Response(200, json=[])
        if p == "/api/infra/network/ingresses":
            return httpx.Response(200, json=[])
        if p == "/api/infra/network/policies":
            return httpx.Response(200, json=[])
        if p == "/api/infra/monitoring/metrics/cluster":
            return httpx.Response(200, json={})
        if p == "/api/infra/monitoring/metrics/gpus":
            return httpx.Response(200, json={})
        if p == "/api/infra/monitoring/alerts/rules":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.infra_client = InfraAPIClient(InfraAPIClientConfig(base_url="http://infra", transport=transport))
    return TestClient(app)


def test_meta_endpoints(client):
    r = client.get("/api/infra/status")
    assert r.status_code == 200
    assert r.json().get("status") == "success"

    r = client.get("/api/infra/health")
    assert r.status_code == 200
    assert r.json().get("status") == "success"

    r = client.get("/api/infra/metrics")
    assert r.status_code == 200
    assert r.json().get("status") == "success"


def test_nodes_and_services(client):
    r = client.get("/api/infra/nodes")
    assert r.status_code == 200

    r = client.get("/api/infra/services")
    assert r.status_code == 200


def test_scheduler_storage_network_monitoring_smoke(client):
    # scheduler (GET-only subset in management)
    assert client.get("/api/infra/scheduler/quotas").status_code == 200
    assert client.get("/api/infra/scheduler/tasks").status_code == 200

    # storage
    assert client.get("/api/infra/storage/pvcs").status_code == 200
    assert client.get("/api/infra/storage/collections").status_code == 200

    # network
    assert client.get("/api/infra/network/services").status_code == 200
    assert client.get("/api/infra/network/ingresses").status_code == 200
    assert client.get("/api/infra/network/policies").status_code == 200

    # monitoring
    assert client.get("/api/infra/monitoring/metrics/cluster").status_code == 200
    assert client.get("/api/infra/monitoring/metrics/gpus").status_code == 200
    assert client.get("/api/infra/monitoring/alerts/rules").status_code == 200
