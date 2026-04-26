import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_persona_routing_applies_to_children_spawn(tmp_path, monkeypatch):
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

        # Upsert tenant policy routing
        persona_tid = "persona:agency:engineering:engineering-frontend-developer"
        pol = {
            "persona_routing": {
                "routes": [
                    {"match": "skill:demo_readonly_summarize", "persona_template_id": persona_tid, "risk_level": "high"},
                ],
                "defaults_by_kind": {"skill": "persona:agency:engineering:default"},
                "default_risk_by_kind": {"skill": "low"},
                "default_risk_level": "medium",
            }
        }
        up = client.put("/api/core/policies/tenants/t_demo", headers=hdr, json={"policy": pol})
        assert up.status_code == 200, up.text

        # Permission for child skill execution
        r = client.post("/api/core/permissions/grant", json={"user_id": "admin", "resource_id": "demo_readonly_summarize", "permission": "execute"})
        assert r.status_code == 200, r.text

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

        ev = client.get(f"/api/core/runs/{parent_id}/events", params={"after_seq": 0, "limit": 200}, headers=hdr)
        assert ev.status_code == 200, ev.text
        items = ev.json().get("items") or []
        matched = [
            e
            for e in items
            if e.get("type") == "child_run_spawned"
            and (e.get("payload") or {}).get("node_id") == "step_1"
            and (e.get("payload") or {}).get("persona_template_id") == persona_tid
        ]
        assert matched
        p = matched[-1].get("payload") or {}
        assert p.get("persona_template_id") == persona_tid
        assert p.get("persona_routed") is True
        assert p.get("risk_level") == "high"
        # request_payload is redacted but should include input._risk_level for skill policy gate
        rp = p.get("request_payload") or {}
        assert (rp.get("input") or {}).get("_risk_level") == "high"
