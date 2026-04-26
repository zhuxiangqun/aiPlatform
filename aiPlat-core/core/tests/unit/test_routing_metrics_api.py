import time
import pytest


@pytest.mark.asyncio
async def test_routing_metrics_api_series_and_hist(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    import core.server as srv
    from fastapi.testclient import TestClient

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")
        now = time.time()
        # strict eval eligible for demo_skill, missed once
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "routing_strict_eval",
                "status": "eval",
                "args": {
                    "routing_decision_id": "rtd_x",
                    "strict_eligible": True,
                    "strict_outcome": "miss_tool",
                    "eligible_top1_skill_id": "demo_skill",
                    "coding_policy_profile": "off",
                },
                "created_at": now,
            }
        )
        # explain with score gap and rank for selected demo_skill
        await srv._execution_store.add_syscall_event(
            {
                "trace_id": "t",
                "run_id": "r",
                "tenant_id": "default",
                "kind": "routing",
                "name": "routing_explain",
                "status": "explain",
                "args": {
                    "routing_decision_id": "rtd_x",
                    "selected_kind": "skill",
                    "selected_name": "demo_skill",
                    "score_gap": 2.0,
                    "selected_rank": 1,
                    "coding_policy_profile": "off",
                },
                "created_at": now,
            }
        )

        r = client.get("/api/core/workspace/skills/observability/routing-metrics?since_hours=24&bucket_minutes=60&skill_id=demo_skill")
        assert r.status_code == 200
        js = r.json()
        assert js.get("status") == "ok"
        assert "series" in js and "hists" in js
        assert len((js.get("series") or {}).get("strict_miss_rate") or []) >= 1
        assert (js.get("hists") or {}).get("selected_rank", {}).get("1") == 1

        # profile filter should not include data if mismatched
        r2 = client.get(
            "/api/core/workspace/skills/observability/routing-metrics?since_hours=24&bucket_minutes=60&skill_id=demo_skill&coding_policy_profile=karpathy_v1"
        )
        assert r2.status_code == 200
        js2 = r2.json()
        assert len((js2.get("series") or {}).get("strict_miss_rate") or []) == 0
