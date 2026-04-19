import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_run_contract_v2_tool_success_and_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        ok = client.post(
            "/api/core/tools/calculator/execute",
            json={"expression": "1+2"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body.get("ok") is True
        assert body.get("status") == "completed"
        assert isinstance(body.get("run_id"), str) and body.get("run_id")

        bad = client.post(
            "/api/core/tools/__not_a_tool__/execute",
            json={"foo": "bar"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo"},
        )
        assert bad.status_code == 200
        body2 = bad.json()
        assert body2.get("ok") is False
        assert body2.get("status") in {"failed", "aborted", "timeout"}
        assert isinstance((body2.get("error") or {}).get("code"), str)

