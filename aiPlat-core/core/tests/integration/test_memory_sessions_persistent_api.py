import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_memory_sessions_persist_and_search(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # create a session
        r1 = client.post("/api/core/memory/sessions", json={"metadata": {"user_id": "u1", "agent_type": "default"}})
        assert r1.status_code == 200, r1.text
        sid = r1.json()["session_id"]

        # add messages
        r2 = client.post(
            f"/api/core/memory/sessions/{sid}/messages",
            json={"role": "user", "content": "hello session memory"},
        )
        assert r2.status_code == 200, r2.text
        r3 = client.post(
            f"/api/core/memory/sessions/{sid}/messages",
            json={"role": "assistant", "content": "ack"},
        )
        assert r3.status_code == 200, r3.text

        # search across sessions
        r4 = client.post("/api/core/memory/search", json={"query": "session memory", "limit": 10})
        assert r4.status_code == 200, r4.text
        data = r4.json()
        assert data["total"] >= 1
        assert any("session memory" in (x.get("content") or "") for x in data["results"])
