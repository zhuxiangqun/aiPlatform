import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_onboarding_context_config_updates_env_and_config(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.post(
            "/api/core/onboarding/context-config",
            json={"enable_session_search": True, "context_token_limit": 12345, "require_approval": False},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "updated"

        cfg = client.get("/api/core/diagnostics/context/config")
        assert cfg.status_code == 200, cfg.text
        data = cfg.json()
        assert data.get("enable_session_search") is True
        assert data.get("limits", {}).get("context_token_limit") == 12345

