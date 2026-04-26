import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_run_graph_delta_after_seq(tmp_path, monkeypatch):
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

        # First graph call
        g1 = client.get(f"/api/core/runs/{parent_id}/graph", params={"include_child_summaries": "false", "after_seq": 0}, headers=hdr)
        assert g1.status_code == 200, g1.text
        last_seq = int(g1.json().get("last_seq") or 0)

        # Trigger a new node spawn
        sp = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "c", "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "c"}, "context": {"tenant_id": "t_demo"}}},
        )
        assert sp.status_code == 200, sp.text

        # Incremental graph call
        g2 = client.get(
            f"/api/core/runs/{parent_id}/graph",
            params={"include_child_summaries": "false", "after_seq": last_seq},
            headers=hdr,
        )
        assert g2.status_code == 200, g2.text
        delta = (g2.json().get("delta") or {})
        assert "c" in (delta.get("changed_node_ids") or [])
        nodes_updated = delta.get("nodes_updated") or []
        assert any(n.get("node_id") == "c" for n in nodes_updated)
        nc = [n for n in nodes_updated if n.get("node_id") == "c"][0]
        assert isinstance(nc.get("state"), str) and nc.get("state")
        assert isinstance((nc.get("layout") or {}).get("order"), int)
