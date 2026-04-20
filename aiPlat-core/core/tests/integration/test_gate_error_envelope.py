import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_gate_error_envelope_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_AUTOSMOKE_ENFORCE", "true")

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        # trigger gate: enabling a non-existent skill should be blocked by gate first (targets verified will fail)
        r = client.post("/api/core/skills/does-not-exist/enable")
        assert r.status_code in (403, 409, 400)
        data = r.json()
        d = data.get("detail")
        assert isinstance(d, dict)
        assert "code" in d and "message" in d
        assert "change_id" in d
        assert isinstance(d.get("links"), dict)
        assert isinstance(d.get("next_actions"), list)

