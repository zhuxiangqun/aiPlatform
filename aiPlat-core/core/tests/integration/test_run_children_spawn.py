import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_parent_child_run_spawn_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    # allow running demo_readonly_summarize without approval in this test
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

        # Spawn child
        sp = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={
                "node_id": "step_1",
                "kind": "skill",
                "target_id": "demo_readonly_summarize",
                "payload": {"input": {"text": "hello"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert sp.status_code == 200, sp.text
        child_id = sp.json().get("child_run_id")
        assert isinstance(child_id, str) and child_id

        # List children derived from events
        ls = client.get(f"/api/core/runs/{parent_id}/children", headers=hdr)
        assert ls.status_code == 200, ls.text
        items = ls.json().get("items") or []
        assert any(it.get("child_run_id") == child_id and it.get("node_id") == "step_1" for it in items)

        # Child should have linkage event
        ev = client.get(f"/api/core/runs/{child_id}/events", params={"after_seq": 0, "limit": 200}, headers=hdr)
        assert ev.status_code == 200, ev.text
        evs = ev.json().get("items") or []
        assert any(e.get("type") == "child_run_parent" and (e.get("payload") or {}).get("parent_run_id") == parent_id for e in evs)

