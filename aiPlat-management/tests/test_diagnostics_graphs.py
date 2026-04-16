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
        if p == "/api/core/graphs/runs":
            return httpx.Response(200, json={"runs": [{"run_id": "r1"}], "total": 1, "limit": 50, "offset": 0})
        if p == "/api/core/graphs/runs/r1":
            return httpx.Response(200, json={"run_id": "r1", "graph_name": "react"})
        if p == "/api/core/graphs/runs/r1/checkpoints":
            return httpx.Response(200, json={"run_id": "r1", "checkpoints": [{"checkpoint_id": "c1"}], "limit": 50, "offset": 0})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    return TestClient(app)


def test_list_graph_runs(client):
    r = client.get("/api/diagnostics/graphs/core?limit=50&offset=0")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert "runs" in payload


def test_get_graph_run_with_checkpoints(client):
    r = client.get("/api/diagnostics/graphs/core/r1?include_checkpoints=true")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["run"]["run_id"] == "r1"
    assert payload["checkpoints"]["run_id"] == "r1"

