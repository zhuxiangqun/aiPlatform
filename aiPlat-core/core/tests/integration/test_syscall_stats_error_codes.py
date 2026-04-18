import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_syscall_stats_includes_error_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        store = getattr(server, "_execution_store", None)
        assert store is not None

        async def _seed():
            await store.add_syscall_event(
                {
                    "trace_id": "t1",
                    "run_id": "r1",
                    "kind": "tool",
                    "name": "file_operations",
                    "status": "failed",
                    "error": "policy_denied",
                    "error_code": "POLICY_DENIED",
                    "target_type": "agent",
                    "target_id": "a1",
                }
            )
            await store.add_syscall_event(
                {
                    "trace_id": "t2",
                    "run_id": "r2",
                    "kind": "tool",
                    "name": "file_operations",
                    "status": "failed",
                    "error": "policy_denied",
                    "error_code": "POLICY_DENIED",
                    "target_type": "agent",
                    "target_id": "a1",
                }
            )
            await store.add_syscall_event(
                {
                    "trace_id": "t3",
                    "run_id": "r3",
                    "kind": "llm",
                    "name": "generate",
                    "status": "failed",
                    "error": "no_model",
                    "error_code": "NO_MODEL",
                    "target_type": "agent",
                    "target_id": "a2",
                }
            )

        anyio.run(_seed)

        r = client.get("/api/core/syscalls/stats", params={"window_hours": 24, "top_n": 10})
        assert r.status_code == 200
        data = r.json()
        top = data.get("top_error_codes") or []
        # should include POLICY_DENIED as top
        assert any((x.get("error_code") == "POLICY_DENIED" and int(x.get("count") or 0) >= 2) for x in top)

