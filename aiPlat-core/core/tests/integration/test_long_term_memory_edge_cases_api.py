import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_long_term_memory_default_user_and_limit_behavior(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Add memories without specifying user_id -> should default to "system"
        r1 = client.post("/api/core/memory/longterm", json={"content": "commonword alpha", "metadata": {"n": 1}})
        assert r1.status_code == 200, r1.text
        m1 = r1.json()
        assert m1["user_id"] == "system"

        r2 = client.post("/api/core/memory/longterm", json={"content": "commonword beta", "metadata": {"n": 2}})
        assert r2.status_code == 200, r2.text
        m2 = r2.json()
        assert m2["user_id"] == "system"

        # Search without user_id -> should default to "system"
        s1 = client.post("/api/core/memory/longterm/search", json={"query": "commonword", "limit": 10})
        assert s1.status_code == 200, s1.text
        data = s1.json()
        assert any(x["id"] == m1["id"] for x in data["items"])
        assert any(x["id"] == m2["id"] for x in data["items"])

        # limit should be respected
        s2 = client.post("/api/core/memory/longterm/search", json={"query": "commonword", "limit": 1})
        assert s2.status_code == 200, s2.text
        data2 = s2.json()
        assert len(data2["items"]) == 1
        assert data2["total"] == 1

        # limit=0 -> empty list
        s3 = client.post("/api/core/memory/longterm/search", json={"query": "commonword", "limit": 0})
        assert s3.status_code == 200, s3.text
        data3 = s3.json()
        assert data3["items"] == []
        assert data3["total"] == 0
