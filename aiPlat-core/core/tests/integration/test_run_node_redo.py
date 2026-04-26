import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_node_redo_spawns_new_child_and_invalidates_downstream(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"demo_readonly_summarize":"allow","*":"ask"}')

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Seed a parent run_start (workflow run)
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

        # Spawn step_1
        sp1 = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={
                "node_id": "step_1",
                "kind": "skill",
                "target_id": "demo_readonly_summarize",
                "payload": {"input": {"text": "hello"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert sp1.status_code == 200, sp1.text
        child1 = sp1.json().get("child_run_id")
        assert isinstance(child1, str) and child1

        # Spawn step_2 depends_on step_1
        sp2 = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={
                "node_id": "step_2",
                "depends_on": ["step_1"],
                "kind": "skill",
                "target_id": "demo_readonly_summarize",
                "payload": {"input": {"text": "world"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert sp2.status_code == 200, sp2.text
        child2 = sp2.json().get("child_run_id")
        assert isinstance(child2, str) and child2

        # Redo step_1 with patch; should spawn new child and invalidate step_2 child
        redo = client.post(
            f"/api/core/runs/{parent_id}/nodes/step_1/redo",
            headers=hdr,
            json={"patch": {"input": {"text": "hello!!!"}}},
        )
        assert redo.status_code == 200, redo.text
        body = redo.json()
        new_child = body.get("child_run_id")
        assert isinstance(new_child, str) and new_child and new_child != child1
        inv = body.get("invalidated") or []
        assert any(x.get("child_run_id") == child2 and x.get("node_id") == "step_2" for x in inv)

        # Downstream child should have "stale" event
        ev = client.get(f"/api/core/runs/{child2}/events", params={"after_seq": 0, "limit": 200}, headers=hdr)
        assert ev.status_code == 200, ev.text
        evs = ev.json().get("items") or []
        assert any(e.get("type") == "stale" for e in evs)

