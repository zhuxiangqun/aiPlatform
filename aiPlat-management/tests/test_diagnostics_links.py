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
        if p == "/api/core/executions/e1/trace":
            return httpx.Response(200, json={"trace_id": "t1", "spans": []})
        if p == "/api/core/traces/t1":
            return httpx.Response(200, json={"trace_id": "t1", "spans": []})
        if p == "/api/core/traces/t1/executions":
            return httpx.Response(200, json={"trace_id": "t1", "items": {"agent_executions": [], "skill_executions": []}, "limit": 50, "offset": 0})
        if p == "/api/core/graphs/runs":
            # management queries with trace_id=t1
            return httpx.Response(200, json={"runs": [{"run_id": "r1", "trace_id": "t1"}], "total": 1, "limit": 50, "offset": 0})
        if p == "/api/core/graphs/runs/r1":
            return httpx.Response(200, json={"run_id": "r1", "trace_id": "t1", "parent_run_id": None, "initial_state": {"metadata": {"trace_id": "t1"}}})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    return TestClient(app)


def test_links_by_execution_id(client):
    r = client.get("/api/diagnostics/links/core?execution_id=e1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["resolved"]["trace_id"] == "t1"
    assert payload["graph_runs"]["total"] == 1


def test_links_by_run_id(client):
    r = client.get("/api/diagnostics/links/core?run_id=r1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["resolved"]["trace_id"] == "t1"


def test_links_include_spans_toggle(client):
    r = client.get("/api/diagnostics/links/core?trace_id=t1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["trace"].get("trace_id") == "t1"
    # default include_spans=false => spans stripped
    assert "spans" not in payload["trace"]

    r = client.get("/api/diagnostics/links/core?trace_id=t1&include_spans=true")
    assert r.status_code == 200
    payload = r.json()
    assert "spans" in payload["trace"]


def test_links_graph_run_id_alias(client):
    r = client.get("/api/diagnostics/links/core?graph_run_id=r1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["resolved"]["run_id"] == "r1"


def test_links_ui_summary(client):
    r = client.get("/api/diagnostics/links/core/ui?trace_id=t1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert "summary" in payload
    assert payload["summary"]["trace_id"] == "t1"
