import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_run_checkpoint_request_wait_and_resolve(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Create a "running" run by only writing run_start (no run_end yet).
        # NOTE: kernel runtime is initialized on app startup, so we must enter TestClient first.
        from core.harness.kernel.runtime import get_kernel_runtime
        from core.utils.ids import new_prefixed_id
        import anyio

        rt = get_kernel_runtime()
        assert rt and rt.execution_store
        run_id = new_prefixed_id("run")

        async def _seed():
            await rt.execution_store.append_run_event(
                run_id=run_id,
                event_type="run_start",
                trace_id="trace-test",
                tenant_id="t_demo",
                payload={
                    "kind": "agent",
                    "agent_id": "agent_1",
                    "user_id": "admin",
                    "session_id": "s1",
                    "request_payload": {"messages": [{"role": "user", "content": "hi"}], "context": {"tenant_id": "t_demo"}},
                },
            )

        anyio.run(_seed)

        rq = client.post(
            f"/api/core/runs/{run_id}/checkpoints/request",
            headers=hdr,
            json={"node_id": "B->C", "title": "发布前审核", "risk_level": "high", "blocking": True},
        )
        assert rq.status_code == 200, rq.text
        checkpoint_id = rq.json().get("checkpoint_id")
        assert isinstance(checkpoint_id, str) and checkpoint_id

        w1 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers=hdr,
            json={"timeout_ms": 3000, "after_seq": 0},
        )
        assert w1.status_code == 200, w1.text
        body = w1.json()
        assert body.get("done") is True
        assert (body.get("checkpoint") or {}).get("checkpoint_id") == checkpoint_id
        last_seq = int(body.get("last_seq") or 0)

        rs = client.post(
            f"/api/core/runs/{run_id}/checkpoints/{checkpoint_id}/resolve",
            headers=hdr,
            json={"decision": "approved", "comments": "ok"},
        )
        assert rs.status_code == 200, rs.text

        w2 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers=hdr,
            json={"timeout_ms": 3000, "after_seq": last_seq},
        )
        assert w2.status_code == 200, w2.text
        events = w2.json().get("events") or []
        assert any(e.get("type") == "checkpoint_resolved" for e in events)
