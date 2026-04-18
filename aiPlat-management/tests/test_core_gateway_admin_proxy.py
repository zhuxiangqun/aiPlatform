import httpx
import pytest
from fastapi.testclient import TestClient

from management.server import create_app
from management.core_client import CoreAPIClient, CoreAPIClientConfig


@pytest.fixture
def client():
    app = create_app()

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/api/core/gateway/pairings":
            if request.method == "GET":
                return httpx.Response(200, json={"items": [{"id": "p1", "channel": "slack", "channel_user_id": "U1", "user_id": "u1"}], "total": 1, "limit": 100, "offset": 0})
            if request.method == "POST":
                return httpx.Response(200, json={"id": "p1", "channel": "slack", "channel_user_id": "U1", "user_id": "u1"})
            if request.method == "DELETE":
                return httpx.Response(200, json={"status": "deleted"})
        if p == "/api/core/gateway/tokens":
            if request.method == "GET":
                return httpx.Response(200, json={"items": [{"id": "t1", "name": "token1", "enabled": 1}], "total": 1, "limit": 100, "offset": 0})
            if request.method == "POST":
                return httpx.Response(200, json={"id": "t1", "name": "token1", "enabled": 1})
        if p == "/api/core/gateway/tokens/t1" and request.method == "DELETE":
            return httpx.Response(200, json={"status": "deleted"})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    import management.api.core as core_api

    core_api._core_client = app.state.core_client
    return TestClient(app)


def test_gateway_pairings_proxy(client):
    r1 = client.get("/api/core/gateway/pairings?limit=100&offset=0")
    assert r1.status_code == 200
    assert r1.json()["total"] == 1

    r2 = client.post("/api/core/gateway/pairings", json={"channel": "slack", "channel_user_id": "U1", "user_id": "u1"})
    assert r2.status_code == 200

    r3 = client.delete("/api/core/gateway/pairings?channel=slack&channel_user_id=U1")
    assert r3.status_code == 200


def test_gateway_tokens_proxy(client):
    r1 = client.get("/api/core/gateway/tokens?limit=100&offset=0")
    assert r1.status_code == 200
    assert r1.json()["total"] == 1

    r2 = client.post("/api/core/gateway/tokens", json={"name": "token1", "token": "secret"})
    assert r2.status_code == 200

    r3 = client.delete("/api/core/gateway/tokens/t1")
    assert r3.status_code == 200

