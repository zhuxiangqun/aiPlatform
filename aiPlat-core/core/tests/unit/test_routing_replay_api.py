import time
import pytest


@pytest.mark.asyncio
async def test_routing_replay_api_returns_bundle(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    import core.server as srv
    from fastapi.testclient import TestClient

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")
        now = time.time()
        # routing decision + explain + strict
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "routing_decision",
                "status": "decision",
                "args": {"routing_decision_id": "rtd_x", "selected_kind": "skill", "selected_name": "demo_skill"},
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
                "args": {"routing_decision_id": "rtd_x", "query_excerpt": "hi", "candidates_top": [{"skill_id": "demo_skill", "score": 5}]},
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
                "name": "routing_strict_eval",
                "status": "eval",
                "args": {"routing_decision_id": "rtd_x", "strict_outcome": "hit"},
                "created_at": now,
            }
        )
        r = client.get("/api/core/workspace/skills/observability/routing-replay?routing_decision_id=rtd_x&since_hours=24&limit=2000")
        assert r.status_code == 200
        js = r.json()
        assert js.get("status") == "ok"
        assert js.get("routing_decision_id") == "rtd_x"
        assert js.get("decision") is not None
        assert js.get("explain") is not None
        assert js.get("strict") is not None

