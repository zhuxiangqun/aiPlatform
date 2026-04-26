import time
import pytest


@pytest.mark.asyncio
async def test_routing_funnel_api_smoke(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    import core.server as srv
    from fastapi.testclient import TestClient

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")

        now = time.time()
        # routing selected
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "skill_route",
                "status": "selected",
                "args": {"skill": "demo_skill", "params_keys": ["prompt"], "routing_decision_id": "rtd_x"},
                "created_at": now,
            }
        )
        # decision total
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "routing_decision",
                "status": "decision",
                "args": {"routing_decision_id": "rtd_x", "selected_kind": "skill", "selected_name": "demo_skill", "selected_skill_id": "demo_skill", "query_excerpt": "帮我看看代码"},
                "created_at": now,
            }
        )
        # candidates snapshot
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "skill_candidates",
                "status": "candidates",
                "args": {
                    "selected_skill": "demo_skill",
                    "query_excerpt": "帮我看看代码",
                    "routing_decision_id": "rtd_x",
                    "candidates": [
                        {"skill_id": "demo_skill", "name": "demo_skill", "scope": "workspace", "score": 9.0},
                        {"skill_id": "y", "name": "other", "scope": "engine", "score": 2.0},
                    ],
                },
                "created_at": now,
            }
        )
        # candidates snapshot from loop/router (should also be included via LIKE filter)
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "skill_candidates_snapshot",
                "status": "snapshot",
                "args": {
                    "selected_kind": "tool",
                    "selected_name": "web_search",
                    "query_excerpt": "帮我看看代码",
                    "routing_decision_id": "rtd_x",
                    "candidates": [{"skill_id": "demo_skill", "name": "demo_skill", "scope": "workspace", "score": 3.0}],
                },
                "created_at": now,
            }
        )
        # execution success
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t2",
                "span_id": "s2",
                "run_id": "r2",
                "tenant_id": "default",
                "kind": "skill",
                "name": "demo_skill",
                "status": "success",
                "duration_ms": 10.0,
                "args": {"params": {}},
                "created_at": now,
            }
        )

        r = client.get("/api/core/workspace/skills/observability/routing-funnel?since_hours=24&limit=2000")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert isinstance(data.get("totals"), dict)
        items = data.get("items") or []
        row = next((x for x in items if x.get("name") == "demo_skill"), None)
        assert row is not None
        assert int(row.get("selected") or 0) >= 1
        assert int(row.get("candidate_any") or 0) >= 1
        assert int(row.get("success") or 0) >= 1
