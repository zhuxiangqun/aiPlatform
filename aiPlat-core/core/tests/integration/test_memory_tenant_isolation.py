import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_memory_search_is_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # tenant A
        r1 = client.post(
            "/api/core/memory/sessions",
            json={"metadata": {}},
            headers={"X-AIPLAT-TENANT-ID": "t_a", "X-AIPLAT-ACTOR-ID": "u1", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert r1.status_code == 200, r1.text
        s1 = r1.json().get("session_id")
        assert isinstance(s1, str) and s1
        client.post(
            f"/api/core/memory/sessions/{s1}/messages",
            json={"role": "user", "content": "TENANT_A_ONLY_hello_123"},
            headers={"X-AIPLAT-TENANT-ID": "t_a", "X-AIPLAT-ACTOR-ID": "u1", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )

        # tenant B
        r2 = client.post(
            "/api/core/memory/sessions",
            json={"metadata": {}},
            headers={"X-AIPLAT-TENANT-ID": "t_b", "X-AIPLAT-ACTOR-ID": "u2", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert r2.status_code == 200, r2.text
        s2 = r2.json().get("session_id")
        assert isinstance(s2, str) and s2
        client.post(
            f"/api/core/memory/sessions/{s2}/messages",
            json={"role": "user", "content": "TENANT_B_ONLY_hello_456"},
            headers={"X-AIPLAT-TENANT-ID": "t_b", "X-AIPLAT-ACTOR-ID": "u2", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )

        # Search under tenant A should NOT see tenant B content
        sa = client.post(
            "/api/core/memory/search",
            json={"query": "TENANT_B_ONLY_hello_456", "limit": 10},
            headers={"X-AIPLAT-TENANT-ID": "t_a", "X-AIPLAT-ACTOR-ID": "u1", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert sa.status_code == 200, sa.text
        assert (sa.json().get("total") or 0) == 0

        sb = client.post(
            "/api/core/memory/search",
            json={"query": "TENANT_A_ONLY_hello_123", "limit": 10},
            headers={"X-AIPLAT-TENANT-ID": "t_b", "X-AIPLAT-ACTOR-ID": "u2", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert sb.status_code == 200, sb.text
        assert (sb.json().get("total") or 0) == 0

