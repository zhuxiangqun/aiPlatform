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
        assert data.get("status") in {"ok", "degraded", "fail"}
        assert data.get("product_id") == "aiplat"
        assert data.get("capability_id") == "aiplat"
        assert data.get("deploy_unit") == "central"
        assert data.get("version") == "0.1.0"
        assert "checks" in data
        assert "db" in data["checks"]
        assert data.get("control_plane", {}).get("schema_version") == "aiplat.control.v0"

        for path, product in (
            ("/api/core/ontology/healthz", "ontology"),
            ("/api/core/eval/healthz", "evaluation"),
            ("/api/core/fde/healthz", "fde"),
        ):
            rr = client.get(path)
            assert rr.status_code == 200, path
            body = rr.json()
            assert body.get("product_id") == product, body
            assert body.get("version") == "0.1.0", body
            assert body.get("status") in {"ok", "degraded", "fail"}
        fde = client.get("/api/core/fde/healthz").json()
        assert fde.get("production_field") is True
        assert fde.get("field_d1_adr") == "accepted"

