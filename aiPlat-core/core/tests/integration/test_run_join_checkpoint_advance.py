import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_join_checkpoint_apply_spawns_next_node(tmp_path, monkeypatch):
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

        # Define join with checkpoint and on_approved_spawn next node
        jd = client.post(
            f"/api/core/runs/{parent_id}/joins/define",
            headers=hdr,
            json={
                "node_id": "join_1",
                "required_nodes": ["a", "b"],
                "mode": "all_success",
                "checkpoint_on_ready": {
                    "enabled": True,
                    "title": "汇合后复核",
                    "risk_level": "medium",
                    "blocking": True,
                    "on_approved_spawn": {
                        "node_id": "c",
                        "depends_on": ["a", "b"],
                        "kind": "skill",
                        "target_id": "demo_readonly_summarize",
                        "payload": {"input": {"text": "c"}, "context": {"tenant_id": "t_demo"}},
                    },
                },
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
        ckpt = jw.json().get("checkpoint_id")
        assert isinstance(ckpt, str) and ckpt

        # Approve checkpoint
        rs = client.post(
            f"/api/core/runs/{parent_id}/checkpoints/{ckpt}/resolve",
            headers=hdr,
            json={"decision": "approved", "comments": "go"},
        )
        assert rs.status_code == 200, rs.text

        # Apply checkpoint to spawn next node
        ap = client.post(
            f"/api/core/runs/{parent_id}/checkpoints/{ckpt}/apply",
            headers=hdr,
            json={},
        )
        assert ap.status_code == 200, ap.text
        out = ap.json()
        assert out.get("action") == "spawn"
        child = (out.get("child") or {}).get("child_run_id")
        assert isinstance(child, str) and child

        # Parent children should include node c
        ls = client.get(f"/api/core/runs/{parent_id}/children", headers=hdr)
        assert ls.status_code == 200, ls.text
        items = ls.json().get("items") or []
        assert any(it.get("node_id") == "c" and it.get("child_run_id") == child for it in items)

