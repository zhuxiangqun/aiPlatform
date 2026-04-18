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
        if p == "/api/core/syscalls/events":
            return httpx.Response(200, json={"items": [{"id": "se1", "kind": "tool", "name": "file_operations", "status": "ok"}], "total": 1})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    return TestClient(app)


def test_syscalls_list_core(client):
    r = client.get("/api/diagnostics/syscalls/core?kind=tool&limit=10&offset=0")
    assert r.status_code == 200
    payload = r.json()
    assert payload["supported"] is True
    assert payload["layer"] == "core"
    assert payload["syscalls"]["total"] == 1

