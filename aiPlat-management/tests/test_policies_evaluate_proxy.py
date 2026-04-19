import httpx
import pytest
from fastapi.testclient import TestClient

from management.server import create_app
from management.core_client import CoreAPIClient, CoreAPIClientConfig


@pytest.fixture
def client():
    app = create_app()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/core/policies/evaluate" and request.method == "POST":
            return httpx.Response(200, json={"final_decision": "deny", "policy": {"decision": "deny"}})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    # align module singleton
    try:
        from management.api import core as _core_api

        _core_api._core_client = app.state.core_client
    except Exception:
        pass
    return TestClient(app)


def test_policies_evaluate_proxy(client):
    r = client.post("/api/policies/evaluate", json={"kind": "tool", "tool_name": "calculator"})
    assert r.status_code == 200
    assert r.json()["final_decision"] == "deny"

