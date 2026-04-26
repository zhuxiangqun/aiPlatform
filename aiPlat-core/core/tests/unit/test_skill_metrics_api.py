import time
import anyio
import pytest


@pytest.mark.asyncio
async def test_skill_metrics_api_smoke(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    import core.server as srv
    from fastapi.testclient import TestClient

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")  # init lifespan

        now = time.time()
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t1",
                "span_id": "s1",
                "run_id": "r1",
                "tenant_id": "default",
                "kind": "skill",
                "name": "demo_skill",
                "status": "success",
                "start_time": now - 0.2,
                "end_time": now,
                "duration_ms": 200.0,
                "args": {"params": {"x": 1}},
                "result": {"output": "ok"},
                "user_id": "u1",
                "session_id": "sess",
                "created_at": now,
            }
        )

        r = client.get("/api/core/workspace/skills/observability/skill-metrics?since_hours=24&limit=2000")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        items = data.get("items") or []
        assert any(it.get("name") == "demo_skill" for it in items)

