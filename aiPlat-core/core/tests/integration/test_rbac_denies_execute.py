import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_rbac_enforced_denies_execute(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "enforced")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/tools/calculator/execute",
            json={"expression": "1+1", "user_id": "u1", "session_id": "s1"},
            headers={"X-AIPLAT-ACTOR-ROLE": "viewer", "X-AIPLAT-ACTOR-ID": "u_view", "X-AIPLAT-TENANT-ID": "t_demo"},
        )
        assert r.status_code == 403, r.text
        body = r.json()
        assert body.get("ok") is False
        assert (body.get("error") or {}).get("code") == "FORBIDDEN"

