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
        if p == "/api/core/change-control/changes":
            return httpx.Response(
                200,
                json={
                    "items": [{"change_id": "chg-1", "name": "gate:skill.enable", "status": "blocked", "created_at": 1.0}],
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                },
            )
        if p == "/api/core/change-control/changes/chg-1":
            return httpx.Response(
                200,
                json={
                    "change_id": "chg-1",
                    "latest": {"id": "se1", "name": "gate:skill.enable", "status": "blocked"},
                    "events": {"items": [{"id": "se1"}], "total": 1, "limit": 200, "offset": 0},
                },
            )
        if p == "/api/core/change-control/changes/chg-1/autosmoke":
            return httpx.Response(200, json={"status": "ok", "change_id": "chg-1", "results": [{"type": "skill", "id": "s1", "enqueued": True}]})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    return TestClient(app)


def test_change_control_list_core(client):
    r = client.get("/api/diagnostics/change-control/core?limit=10&offset=0")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["layer"] == "core"
    assert payload["changes"]["total"] == 1


def test_change_control_detail_core(client):
    r = client.get("/api/diagnostics/change-control/core/chg-1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["layer"] == "core"
    assert payload["change"]["change_id"] == "chg-1"


def test_change_control_autosmoke_core(client):
    r = client.post("/api/diagnostics/change-control/core/chg-1/autosmoke")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["layer"] == "core"
    assert payload["result"]["change_id"] == "chg-1"
