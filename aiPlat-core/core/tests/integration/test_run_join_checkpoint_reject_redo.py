import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_join_checkpoint_reject_apply_redo_node_invalidates_downstream(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"demo_readonly_summarize":"allow","*":"ask"}')
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "enforced")

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

        # Spawn required nodes a/b
        a = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "a", "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "a"}, "context": {"tenant_id": "t_demo"}}},
        )
        assert a.status_code == 200, a.text
        a_child = a.json().get("child_run_id")
        assert isinstance(a_child, str) and a_child

        b = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "b", "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "b"}, "context": {"tenant_id": "t_demo"}}},
        )
        assert b.status_code == 200, b.text

        # Spawn downstream node d depends_on a (should be invalidated if a is redone)
        d = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={
                "node_id": "d",
                "depends_on": ["a"],
                "kind": "skill",
                "target_id": "demo_readonly_summarize",
                "payload": {"input": {"text": "d"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert d.status_code == 200, d.text
        d_child = d.json().get("child_run_id")
        assert isinstance(d_child, str) and d_child

        # Define join with checkpoint + rejected redo action
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
                    "on_rejected_redo_node": {"node_id": "a"},
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

        # Reject checkpoint
        rs = client.post(
            f"/api/core/runs/{parent_id}/checkpoints/{ckpt}/resolve",
            headers=hdr,
            json={"decision": "rejected", "comments": "redo a"},
        )
        assert rs.status_code == 200, rs.text

        # Apply checkpoint should redo node a and invalidate downstream d
        ap = client.post(
            f"/api/core/runs/{parent_id}/checkpoints/{ckpt}/apply",
            headers=hdr,
            json={},
        )
        assert ap.status_code == 200, ap.text
        out = ap.json()
        assert out.get("action") == "redo_node"
        redo_child = ((out.get("redo") or {}).get("child_run_id"))
        assert isinstance(redo_child, str) and redo_child and redo_child != a_child

        # Downstream d should have "stale" event
        ev = client.get(f"/api/core/runs/{d_child}/events", params={"after_seq": 0, "limit": 200}, headers=hdr)
        assert ev.status_code == 200, ev.text
        evs = ev.json().get("items") or []
        assert any(e.get("type") == "stale" for e in evs)

