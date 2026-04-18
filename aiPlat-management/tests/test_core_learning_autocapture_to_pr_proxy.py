import httpx
import pytest
from fastapi.testclient import TestClient

from management.server import create_app
from management.core_client import CoreAPIClient, CoreAPIClientConfig


@pytest.fixture
def client():
    app = create_app()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/core/learning/autocapture/to_prompt_revision" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "prompt_revision": {"artifact_id": "pr-1", "kind": "prompt_revision"},
                    "release_candidate": {"artifact_id": "rc-1", "kind": "release_candidate"},
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url="http://core", transport=transport))
    import management.api.core as core_api

    core_api._core_client = app.state.core_client
    return TestClient(app)


def test_learning_autocapture_to_prompt_revision_proxy(client):
    r = client.post("/api/core/learning/autocapture/to_prompt_revision", json={"artifact_id": "auto-1", "create_release_candidate": True})
    assert r.status_code == 200
    data = r.json()
    assert data["prompt_revision"]["kind"] == "prompt_revision"

