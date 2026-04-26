import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_children_spawn_persists_persona_template_id_in_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"demo_readonly_summarize":"allow","*":"ask"}')

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
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

        persona_tid = "persona:agency:engineering:engineering-frontend-developer"
        sp = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={
                "node_id": "step_1",
                "kind": "skill",
                "target_id": "demo_readonly_summarize",
                "persona_template_id": persona_tid,
                "payload": {"input": {"text": "hello"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert sp.status_code == 200, sp.text

        ev = client.get(f"/api/core/runs/{parent_id}/events", params={"after_seq": 0, "limit": 200}, headers=hdr)
        assert ev.status_code == 200, ev.text
        items = ev.json().get("items") or []
        assert any(e.get("type") == "child_run_spawned" and (e.get("payload") or {}).get("persona_template_id") == persona_tid for e in items)

