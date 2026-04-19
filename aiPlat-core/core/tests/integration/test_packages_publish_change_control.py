import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_packages_publish_approval_required_returns_change_id(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ENV", "prod")
    monkeypatch.setenv("AIPLAT_PACKAGES_FORCE_APPROVAL_IN_PROD", "true")

    import core.server as server

    importlib.reload(server)

    # stub globals for approval-required early path
    server._execution_store = object()

    class FakeReq:
        def __init__(self, request_id: str):
            self.request_id = request_id

    class FakeApprovalMgr:
        def register_rule(self, rule):
            return None

        def create_request(self, ctx, rule=None):
            return FakeReq("apr-2")

    server._approval_manager = FakeApprovalMgr()

    with TestClient(server.app) as client:
        r = client.post("/api/core/packages/demo/publish", json={"version": "1.0.0"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "approval_required"
        assert str(data.get("change_id") or "").startswith("chg-")

