import httpx
import pytest
from fastapi.testclient import TestClient

from management.server import create_app
from management.infra_client import InfraAPIClient, InfraAPIClientConfig


@pytest.fixture
def client():
    app = create_app()

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/api/infra/managers":
            return httpx.Response(200, json={"status": "success", "data": ["node", "service"]})
        if p == "/api/infra/managers/node/config" and request.method == "GET":
            return httpx.Response(200, json={"status": "success", "data": {"name": "node", "config": {"a": 1}}})
        if p == "/api/infra/managers/node/config" and request.method == "PUT":
            return httpx.Response(200, json={"status": "success", "message": "ok"})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.infra_client = InfraAPIClient(InfraAPIClientConfig(base_url="http://infra", transport=transport))
    return TestClient(app)


def test_dashboard_config_list(client):
    r = client.get("/api/dashboard/config")
    assert r.status_code == 200
    assert "managers" in r.json()


def test_dashboard_config_get(client):
    r = client.get("/api/dashboard/config/node")
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("status") == "success"
