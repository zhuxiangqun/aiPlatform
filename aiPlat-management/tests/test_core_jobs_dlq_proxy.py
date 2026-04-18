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
        if p == "/api/core/jobs":
            return httpx.Response(200, json={"items": [{"id": "job-1", "name": "j1"}], "total": 1, "limit": 100, "offset": 0})
        if p == "/api/core/jobs/dlq":
            return httpx.Response(200, json={"items": [{"id": "dlq-1", "job_id": "job-1", "status": "pending"}], "total": 1, "limit": 100, "offset": 0})
        if p == "/api/core/jobs/dlq/dlq-1/retry":
            return httpx.Response(200, json={"ok": True})
        if p == "/api/core/jobs/dlq/dlq-1" and request.method == "DELETE":
            return httpx.Response(200, json={"status": "deleted", "dlq_id": "dlq-1"})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    # core api router uses module-level singleton
    import management.api.core as core_api

    core_api._core_client = app.state.core_client
    return TestClient(app)


def test_core_jobs_proxy_list(client):
    r = client.get("/api/core/jobs?limit=100&offset=0")
    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] == 1


def test_core_jobs_dlq_proxy(client):
    r = client.get("/api/core/jobs/dlq?limit=100&offset=0")
    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] == 1

    r2 = client.post("/api/core/jobs/dlq/dlq-1/retry")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    r3 = client.delete("/api/core/jobs/dlq/dlq-1")
    assert r3.status_code == 200
    assert r3.json()["status"] == "deleted"

