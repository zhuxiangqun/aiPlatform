import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_run_graph_endpoint_contains_nodes_edges_joins_checkpoints(tmp_path, monkeypatch):
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

        persona_tid = "persona:agency:engineering:engineering-frontend-developer"

        client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "a", "kind": "skill", "target_id": "demo_readonly_summarize", "persona_template_id": persona_tid, "payload": {"input": {"text": "a"}, "context": {"tenant_id": "t_demo"}}},
        )
        client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "b", "depends_on": ["a"], "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "b"}, "context": {"tenant_id": "t_demo"}}},
        )

        jd = client.post(
            f"/api/core/runs/{parent_id}/joins/define",
            headers=hdr,
            json={"node_id": "join_1", "required_nodes": ["a", "b"], "mode": "all_success", "checkpoint_on_ready": {"enabled": True}},
        )
        assert jd.status_code == 200, jd.text
        join_id = jd.json().get("join_id")
        jw = client.post(f"/api/core/runs/{parent_id}/joins/{join_id}/wait", headers=hdr, json={"timeout_ms": 20000, "after_seq": 0})
        assert jw.status_code == 200, jw.text
        assert isinstance(jw.json().get("checkpoint_id"), str)

        g = client.get(f"/api/core/runs/{parent_id}/graph", params={"include_child_summaries": "true"}, headers=hdr)
        assert g.status_code == 200, g.text
        body = g.json()
        assert body["run_id"] == parent_id
        nodes = body.get("nodes") or []
        edges = body.get("edges") or []
        joins = body.get("joins") or []
        checkpoints = body.get("checkpoints") or []
        topo = body.get("topo_order") or []
        assert any(n.get("node_id") == "a" for n in nodes)
        assert any(n.get("node_id") == "b" for n in nodes)
        assert any(e.get("from") == "a" and e.get("to") == "b" for e in edges)
        assert any(j.get("join_id") == join_id for j in joins)
        assert any((c.get("requested") or {}).get("checkpoint_id") for c in checkpoints)
        assert isinstance(topo, list) and topo
        assert all(isinstance(x, str) for x in topo)
        # layout/state hints
        na = [n for n in nodes if n.get("node_id") == "a"][0]
        assert isinstance((na.get("layout") or {}).get("order"), int)
        assert isinstance(na.get("state"), str) and na.get("state")
        assert isinstance(joins[0].get("state"), str) and joins[0].get("state")
        assert isinstance(checkpoints[0].get("state"), str) and checkpoints[0].get("state")
