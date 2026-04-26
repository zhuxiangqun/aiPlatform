import time
import pytest


@pytest.mark.asyncio
async def test_routing_explain_api_filters_by_skill_id(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    import core.server as srv
    from fastapi.testclient import TestClient

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")
        now = time.time()
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "routing_explain",
                "status": "explain",
                "args": {"routing_decision_id": "rtd_x", "selected_kind": "skill", "selected_skill_id": "demo_skill", "selected_name": "demo_skill"},
                "created_at": now,
            }
        )
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "routing_explain",
                "status": "explain",
                "args": {"routing_decision_id": "rtd_y", "selected_kind": "skill", "selected_skill_id": "other", "selected_name": "other"},
                "created_at": now,
            }
        )
        r = client.get("/api/core/workspace/skills/observability/routing-explain?since_hours=24&limit=50&skill_id=demo_skill&selected_kind=skill")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        items = data.get("items") or []
        assert len(items) == 1
        assert items[0].get("selected_name") == "demo_skill"

