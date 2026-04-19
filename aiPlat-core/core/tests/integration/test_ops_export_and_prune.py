import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_ops_export_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        headers = {"X-AIPLAT-TENANT-ID": "t1", "X-AIPLAT-ACTOR-ID": "system", "X-AIPLAT-ACTOR-ROLE": "admin"}
        store = getattr(server, "_execution_store", None)
        assert store is not None

        # ensure audit log exists
        client.put("/api/core/quota/snapshot", json={"tenant_id": "t1", "quota": {"daily": {"tool_calls": 1}}}, headers=headers)

        async def _seed():
            await store.upsert_approval_request(
                {
                    "request_id": "apr_1",
                    "user_id": "system",
                    "operation": "tool:code",
                    "details": "seed",
                    "rule_id": "seed",
                    "rule_type": "sensitive_operation",
                    "status": "pending",
                    "amount": 1,
                    "batch_size": 1,
                    "is_first_time": False,
                    "tenant_id": "t1",
                    "actor_id": "system",
                    "actor_role": "admin",
                    "session_id": "s1",
                    "run_id": "run_seed",
                    "metadata": {"system_run_plan": {"type": "seed"}},
                    "result": {},
                }
            )
            await store.add_tenant_usage(tenant_id="t1", metric_key="tool_calls", amount=1.0)
            await store.add_connector_delivery_attempt(
                connector="slack",
                tenant_id="t1",
                run_id="run_seed",
                attempt=1,
                url="http://example.com/resp",
                status="failed",
                response_status=500,
                error="nope",
                payload={"text": "x"},
            )

        anyio.run(_seed)

        r = client.get("/api/core/ops/export/audit_logs.csv", params={"tenant_id": "t1", "limit": 50}, headers=headers)
        assert r.status_code == 200
        assert "text/csv" in (r.headers.get("content-type") or "")
        assert b"tenant_id" in r.content

        s = client.get("/api/core/ops/export/syscall_events.csv", params={"tenant_id": "t1", "limit": 50}, headers=headers)
        assert s.status_code == 200
        assert "text/csv" in (s.headers.get("content-type") or "")
        assert b"trace_id" in s.content

        a = client.get("/api/core/ops/export/approvals.csv", params={"tenant_id": "t1", "limit": 50}, headers=headers)
        assert a.status_code == 200
        assert b"request_id" in a.content

        u = client.get("/api/core/ops/export/tenant_usage.csv", params={"tenant_id": "t1", "limit": 50}, headers=headers)
        assert u.status_code == 200
        assert b"metric_key" in u.content

        c = client.get("/api/core/ops/export/connector_attempts.csv", params={"tenant_id": "t1", "limit": 50}, headers=headers)
        assert c.status_code == 200
        assert b"connector" in c.content

        # prune should succeed (best-effort)
        p = client.post("/api/core/ops/prune", json={"now_ts": 1e12}, headers=headers)
        assert p.status_code == 200
        assert p.json().get("ok") is True
