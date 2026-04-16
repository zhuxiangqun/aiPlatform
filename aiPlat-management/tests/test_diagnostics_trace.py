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
        if p == "/api/core/traces":
            return httpx.Response(200, json={"traces": [{"trace_id": "t1"}], "total": 1, "limit": 50, "offset": 0})
        if p == "/api/core/traces/t1":
            return httpx.Response(200, json={"trace_id": "t1", "spans": []})
        if p == "/api/core/traces/t1/executions":
            return httpx.Response(200, json={"trace_id": "t1", "items": {"agent_executions": [], "skill_executions": []}, "limit": 50, "offset": 0})
        if p == "/api/core/executions/e1/trace":
            return httpx.Response(200, json={"trace_id": "t-from-exec", "spans": []})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    return TestClient(app)


def test_trace_list(client):
    r = client.get("/api/diagnostics/trace/core")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["mode"] == "list"
    assert "traces" in payload


def test_trace_by_trace_id(client):
    r = client.get("/api/diagnostics/trace/core?trace_id=t1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["mode"] == "by_trace_id"
    assert payload["trace"]["trace_id"] == "t1"


def test_trace_by_execution_id(client):
    r = client.get("/api/diagnostics/trace/core?execution_id=e1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["mode"] == "by_execution_id"
    assert payload["trace"]["trace_id"] == "t-from-exec"

