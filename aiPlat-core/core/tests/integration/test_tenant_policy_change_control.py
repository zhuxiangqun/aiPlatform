import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tenant_policy_upsert_returns_change_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.put(
            "/api/core/policies/tenants/t-1",
            json={"policy": {"tool_policy": {"deny_tools": [], "approval_required_tools": []}}, "version": None, "actor_id": "admin"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("tenant_id") == "t-1"
        assert isinstance(data.get("change_id"), str) and data["change_id"].startswith("chg-")
        assert isinstance(data.get("links"), dict)

