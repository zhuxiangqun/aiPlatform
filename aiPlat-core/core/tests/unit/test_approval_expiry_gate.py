import time
import anyio
from fastapi.testclient import TestClient


def test_approval_expired_cannot_be_approved():
    import core.server as srv

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")

        rid = "req_expired_test"
        now = time.time()
        record = {
            "request_id": rid,
            "user_id": "admin",
            "operation": "config:publish",
            "details": "expired test",
            "rule_id": "x",
            "rule_type": "sensitive_operation",
            "status": "pending",
            "amount": None,
            "batch_size": None,
            "is_first_time": False,
            "created_at": now - 3600,
            "updated_at": now - 3600,
            "expires_at": now - 10,
            "metadata": {"tenant_id": "default"},
            "result": None,
        }
        anyio.run(srv._execution_store.upsert_approval_request, record)

        r2 = client.post(f"/api/core/approvals/{rid}/approve", json={"approved_by": "admin", "comments": ""})
        assert r2.status_code == 409
        body = r2.json()
        detail = body.get("detail") if isinstance(body, dict) and "detail" in body else body
        assert isinstance(detail, dict)
        assert detail.get("code") == "approval_expired"

