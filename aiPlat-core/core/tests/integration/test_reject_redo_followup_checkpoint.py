import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_reject_apply_creates_followup_checkpoint(tmp_path, monkeypatch):
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
        a0 = client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "a", "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "a"}, "context": {"tenant_id": "t_demo"}}},
        )
        assert a0.status_code == 200, a0.text
        a0_child = a0.json().get("child_run_id")
        assert isinstance(a0_child, str) and a0_child
        client.post(
            f"/api/core/runs/{parent_id}/children/spawn",
            headers=hdr,
            json={"node_id": "b", "kind": "skill", "target_id": "demo_readonly_summarize", "payload": {"input": {"text": "b"}, "context": {"tenant_id": "t_demo"}}},
        )

        # Define join with checkpoint + rejected redo action
        jd = client.post(
            f"/api/core/runs/{parent_id}/joins/define",
            headers=hdr,
            json={"node_id": "join_1", "required_nodes": ["a", "b"], "mode": "all_success", "checkpoint_on_ready": {"enabled": True, "on_rejected_redo_node": {"node_id": "a"}}},
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

        # Reject with checklist_result
        rs = client.post(
            f"/api/core/runs/{parent_id}/checkpoints/{ckpt}/resolve",
            headers=hdr,
            json={"decision": "rejected", "comments": "needs fixes", "checklist_result": [{"text": "[a] Lighthouse > 90", "status": "failed", "note": "perf too low"}]},
        )
        assert rs.status_code == 200, rs.text

        ap = client.post(f"/api/core/runs/{parent_id}/checkpoints/{ckpt}/apply", headers=hdr, json={})
        assert ap.status_code == 200, ap.text
        follow = ap.json().get("followup_checkpoint_id")
        assert isinstance(follow, str) and follow

        # Ensure follow-up checkpoint_requested exists and links to previous checkpoint
        ev = client.get(f"/api/core/runs/{parent_id}/events", params={"after_seq": 0, "limit": 800}, headers=hdr)
        assert ev.status_code == 200, ev.text
        items = ev.json().get("items") or []
        found = None
        for e in items:
            if e.get("type") == "checkpoint_requested" and (e.get("payload") or {}).get("checkpoint_id") == follow:
                found = e.get("payload") or {}
                break
        assert found is not None
        assert found.get("previous_checkpoint_id") == ckpt
        checklist = found.get("checklist") or []
        assert any("Lighthouse" in (x.get("text") or "") for x in checklist)
        art = (found.get("artifact") or {})
        assert (art.get("redo_child_run_id") or "")
        ep = art.get("evidence_pack") or {}
        assert isinstance(ep.get("syscalls"), list)
        diff = ep.get("diff") or {}
        assert diff.get("prev_run_id") == a0_child
