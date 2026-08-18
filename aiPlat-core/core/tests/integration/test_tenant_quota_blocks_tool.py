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

        # Quota routes migrated to platform (P0-A3); set quota via store directly.
        from core.services.execution_store import get_execution_store
        store = get_execution_store()

        import asyncio

        async def _set_quota(tool_calls: int) -> None:
            await store.upsert_tenant_quota(
                tenant_id="t1",
                quota={"daily": {"tool_calls": tool_calls}},
            )

        # Set quota: tool_calls=0 => tool execution should be blocked
        asyncio.run(_set_quota(0))

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
        asyncio.run(_set_quota(100))

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
        usage = asyncio.run(_read_usage(store, "t1", "tool_calls", day))
        v = 0.0
        for it in usage:
            if it.get("metric_key") == "tool_calls" and it.get("day") == day:
                v = float(it.get("value") or 0)
        assert v >= 2.0


async def _read_usage(store, tenant_id: str, metric_key: str, day: str):
    items = await store.list_tenant_usage(
        tenant_id=tenant_id, metric_key=metric_key,
        day_start=day, day_end=day, limit=50,
    )
    return items or []
