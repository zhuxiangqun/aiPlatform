import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_healthz_returns_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.get("/api/core/healthz")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "checks" in data
        assert "db" in data["checks"]

