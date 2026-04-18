import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tool_execute_emits_tool_start_end_events(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    # Create a file under HOME so file_operations allowlist passes.
    p = tmp_path / "hello.txt"
    p.write_text("hello", encoding="utf-8")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/tools/file_operations/execute",
            json={"operation": "read", "path": str(p), "max_bytes": 1000, "user_id": "u1", "session_id": "s1"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        run_id = body.get("run_id")
        assert isinstance(run_id, str) and run_id.startswith("run_")

        ev = client.get(f"/api/core/runs/{run_id}/events", params={"after_seq": 0, "limit": 50})
        assert ev.status_code == 200, ev.text
        types = [x.get("type") for x in (ev.json().get("items") or [])]
        assert "tool_start" in types
        assert "tool_end" in types

