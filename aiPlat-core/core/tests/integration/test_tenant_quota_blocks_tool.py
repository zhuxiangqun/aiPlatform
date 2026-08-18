import importlib
import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_quota_exceeded_blocks_tool_and_tracks_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # PermissionManager 默认对非 system 用户可能 deny tool execute；测试用 system。
        headers_admin = {"X-AIPLAT-TENANT-ID": "t1", "X-AIPLAT-ACTOR-ID": "system", "X-AIPLAT-ACTOR-ROLE": "admin"}

        # Set quota: tool_calls=0 => tool execution should be blocked
        q = client.put(
            "/api/core/quota/snapshot",
            json={"tenant_id": "t1", "quota": {"daily": {"tool_calls": 0}}},
            headers=headers_admin,
        )
        assert q.status_code == 200, q.text

        r = client.post(
            "/api/core/tools/calculator/execute",
            json={"input": {"expression": "1+2"}, "context": {"tenant_id": "t1", "actor_id": "system", "actor_role": "admin", "session_id": "s1"}},
            headers=headers_admin,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") in ("failed", "completed")
        assert (body.get("error_detail") or {}).get("code") == "QUOTA_EXCEEDED"

        # Allow quota and ensure usage increments
        q2 = client.put(
            "/api/core/quota/snapshot",
            json={"tenant_id": "t1", "quota": {"daily": {"tool_calls": 100}}},
            headers=headers_admin,
        )
        assert q2.status_code == 200, q2.text

        client.post(
            "/api/core/tools/calculator/execute",
            json={"input": {"expression": "2+3"}, "context": {"tenant_id": "t1", "actor_id": "system", "actor_role": "admin", "session_id": "s1"}},
            headers=headers_admin,
        )
        client.post(
            "/api/core/tools/calculator/execute",
            json={"input": {"expression": "3+4"}, "context": {"tenant_id": "t1", "actor_id": "system", "actor_role": "admin", "session_id": "s1"}},
            headers=headers_admin,
        )

        day = time.strftime("%Y-%m-%d", time.gmtime())
        u = client.get(
            "/api/core/quota/usage",
            params={"tenant_id": "t1", "metric_key": "tool_calls", "day_start": day, "day_end": day, "limit": 50},
            headers=headers_admin,
        )
        assert u.status_code == 200, u.text
        items = u.json().get("items") or []
        v = 0.0
        for it in items:
            if it.get("metric_key") == "tool_calls" and it.get("day") == day:
                v = float(it.get("value") or 0)
        assert v >= 2.0
