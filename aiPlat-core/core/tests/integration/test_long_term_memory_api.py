import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_long_term_memory_api_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/memory/longterm",
            json={"user_id": "u1", "key": "k1", "content": "hello api world", "metadata": {"x": 1}},
        )
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["user_id"] == "u1"

        r2 = client.post("/api/core/memory/longterm/search", json={"user_id": "u1", "query": "api", "limit": 10})
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["total"] >= 1
        assert any(x["id"] == rec["id"] for x in data["items"])

