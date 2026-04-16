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
        if p == "/api/core/graphs/runs/r1/resume" and request.method == "POST":
            return httpx.Response(200, json={"run_id": "r2", "checkpoint_id": "c1", "graph_name": "react", "state": {}})
        if p == "/api/core/graphs/runs/r1/resume/execute" and request.method == "POST":
            return httpx.Response(200, json={"parent_run_id": "r1", "run_id": "r2", "checkpoint_id": "c1", "final_state": {"done": True}})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    return TestClient(app)


def test_resume_forward(client):
    r = client.post("/api/diagnostics/graphs/core/r1/resume", json={"checkpoint_id": "c1"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["resumed"]["run_id"] == "r2"


def test_resume_execute_forward(client):
    r = client.post("/api/diagnostics/graphs/core/r1/resume/execute", json={"checkpoint_id": "c1", "max_steps": 3})
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["result"]["parent_run_id"] == "r1"

