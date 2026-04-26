import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_join_ready_triggers_checkpoint_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"demo_readonly_summarize":"allow","*":"ask"}')

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Seed parent run_start
        from core.harness.kernel.runtime import get_kernel_runtime
        from core.utils.ids import new_prefixed_id
        import anyio

        rt = get_kernel_runtime()
        assert rt and rt.execution_store
        parent_id = new_prefixed_id("run")

        async def _seed():
            await rt.execution_store.append_run_event(
                run_id=parent_id,
                event_type="run_start",
                trace_id="trace-parent",
                tenant_id="t_demo",
                payload={"kind": "graph", "graph_name": "workflow", "user_id": "admin", "session_id": "wf1", "request_payload": {"context": {"tenant_id": "t_demo"}}},
            )

        anyio.run(_seed)

        # Permission for child skill execution
        r = client.post("/api/core/permissions/grant", json={"user_id": "admin", "resource_id": "demo_readonly_summarize", "permission": "execute"})
        assert r.status_code == 200, r.text

        # Spawn two children
        client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "a", "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "a"}, "context": {"tenant_id": "t_demo"}}},
        )
        client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "b", "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "b"}, "context": {"tenant_id": "t_demo"}}},
        )

        # Define join with checkpoint_on_ready
        jd = client.post(
            f"/api/core/runs/{parent_id}/joins/define",
            headers=hdr,
            json={
                "node_id": "join_1",
                "required_nodes": ["a", "b"],
                "mode": "all_success",
                "checkpoint_on_ready": {"enabled": True, "title": "汇合后复核", "risk_level": "high", "blocking": True},
            },
        )
        assert jd.status_code == 200, jd.text
        join_id = jd.json().get("join_id")

        jw = client.post(
            f"/api/core/runs/{parent_id}/joins/{join_id}/wait",
            headers=hdr,
            json={"timeout_ms": 20000, "after_seq": 0},
        )
        assert jw.status_code == 200, jw.text
        assert jw.json().get("ready") is True
        ckpt = jw.json().get("checkpoint_id")
        assert isinstance(ckpt, str) and ckpt

        # Parent wait should surface checkpoint
        w = client.post(f"/api/core/runs/{parent_id}/wait", headers=hdr, json={"timeout_ms": 2000, "after_seq": 0})
        assert w.status_code == 200, w.text
        cp = w.json().get("checkpoint") or {}
        assert cp.get("checkpoint_id") == ckpt
        assert cp.get("join_id") == join_id

