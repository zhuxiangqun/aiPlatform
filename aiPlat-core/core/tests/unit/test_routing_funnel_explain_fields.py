import time
import pytest


@pytest.mark.asyncio
async def test_routing_funnel_includes_gap_and_top1_gate_counts(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    import core.server as srv
    from fastapi.testclient import TestClient

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")

        now = time.time()
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
                "args": {"routing_decision_id": "rtd_x", "selected_kind": "skill", "selected_name": "demo_skill", "selected_skill_id": "demo_skill"},
                "created_at": now,
            }
        )
        # candidates snapshot with a denied top1
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
                    "routing_decision_id": "rtd_x",
                    "candidates": [
                        {"skill_id": "top1", "name": "top1", "scope": "engine", "score": 10.0, "perm": "deny", "skill_kind": "rule"},
                        {"skill_id": "demo_skill", "name": "demo_skill", "scope": "workspace", "score": 6.0, "perm": "allow", "skill_kind": "rule"},
                    ],
                },
                "created_at": now,
            }
        )
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
                "args": {"skill": "demo_skill", "routing_decision_id": "rtd_x"},
                "created_at": now,
            }
        )

        # strict eval (eligible exists but selected not eligible -> misroute)
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "span_id": "s",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "routing_strict_eval",
                "status": "eval",
                "args": {
                    "routing_decision_id": "rtd_x",
                    "selected_kind": "skill",
                    "selected_skill_id": "demo_skill",
                    "eligible_top1_skill_id": "top1",
                    "eligible_top1_score": 10.0,
                    "strict_eligible": True,
                    "strict_outcome": "misroute",
                },
                "created_at": now,
            }
        )

        r = client.get("/api/core/workspace/skills/observability/routing-funnel?since_hours=24&limit=2000")
        assert r.status_code == 200
        js = r.json()
        row = next((x for x in (js.get("items") or []) if x.get("name") == "demo_skill"), None)
        assert row is not None
        assert row.get("score_gap_avg") is not None
        assert int(row.get("top1_permission_denied") or 0) >= 1
        assert js.get("strict") is not None
