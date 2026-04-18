import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_learning_autocapture_creates_feedback_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    run_id = "run-1"
    trace_id = "trace-1"

    with TestClient(server.app) as client:
        store = getattr(server, "_execution_store", None)
        assert store is not None

        async def _seed():
            await store.upsert_agent_execution(
                {
                    "id": run_id,
                    "agent_id": "agent_1",
                    "status": "failed",
                    "input": {"message": "hi"},
                    "output": {},
                    "error": "boom",
                    "start_time": 1.0,
                    "end_time": 2.0,
                    "duration_ms": 1000,
                    "trace_id": trace_id,
                    "metadata": {"error_detail": {"code": "EXCEPTION", "message": "boom"}},
                }
            )
            await store.add_syscall_event(
                {
                    "trace_id": trace_id,
                    "run_id": run_id,
                    "kind": "tool",
                    "name": "file_operations",
                    "status": "failed",
                    "error": "permission denied",
                }
            )

        anyio.run(_seed)

        r = client.post(
            "/api/core/learning/autocapture",
            json={"target_type": "agent", "target_id": "agent_1", "run_id": run_id, "trace_id": trace_id, "reason": "ci failure"},
        )
        assert r.status_code == 200, r.text
        art = r.json()
        assert art["kind"] == "feedback_summary"
        assert art["target_type"] == "agent"
        assert art["target_id"] == "agent_1"
        assert art["trace_id"] == trace_id
        assert art["run_id"] == run_id
        assert art["payload"]["feedback"]["syscalls_summary"]["total"] >= 1
