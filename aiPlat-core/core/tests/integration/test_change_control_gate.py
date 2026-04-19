import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_change_id_in_gate_blocked_response(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_AUTOSMOKE_ENFORCE", "true")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post("/api/core/mcp/servers/nonexistent/enable")
        assert r.status_code == 403, r.text
        d = r.json().get("detail") or {}
        assert isinstance(d, dict)
        assert str(d.get("change_id") or "").startswith("chg-")
        links = d.get("links") or {}
        assert isinstance(links, dict)
        assert str(links.get("syscalls_ui") or "").find(str(d.get("change_id"))) >= 0

