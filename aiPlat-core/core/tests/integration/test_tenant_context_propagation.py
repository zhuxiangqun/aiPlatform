import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tenant_id_propagates_to_syscall_events(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        resp = client.post(
            "/api/core/gateway/execute",
            json={
                "channel": "webhook",
                "kind": "tool",
                "target_id": "calculator",
                "payload": {"expression": "2+3"},
            },
            headers={"X-AIPLAT-REQUEST-ID": "req_test_tenant_1", "X-AIPLAT-TENANT-ID": "t_demo"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        run_id = body.get("run_id")
        assert isinstance(run_id, str) and run_id

        store = getattr(server, "_execution_store", None)
        assert store is not None

        res = anyio.run(lambda: store.list_syscall_events(run_id=run_id, limit=50, offset=0))
        items = (res or {}).get("items") or []
        assert items, "expected syscall events to be recorded"
        # At least one syscall event should carry tenant_id
        assert any((it.get("tenant_id") == "t_demo") for it in items)

