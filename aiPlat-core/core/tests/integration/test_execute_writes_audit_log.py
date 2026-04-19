import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tool_execute_writes_audit_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/tools/calculator/execute",
            json={"expression": "2+3", "user_id": "u1", "session_id": "s1"},
            headers={"X-AIPLAT-ACTOR-ID": "u1", "X-AIPLAT-ACTOR-ROLE": "developer", "X-AIPLAT-TENANT-ID": "t_demo"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        run_id = body.get("run_id")
        assert isinstance(run_id, str) and run_id

        a = client.get("/api/core/audit/logs", params={"action": "execute_tool", "run_id": run_id, "limit": 50, "offset": 0})
        assert a.status_code == 200, a.text
        items = a.json().get("items") or []
        assert any(x.get("run_id") == run_id for x in items)

