import time

import anyio


def _make_request():
    """Minimal Starlette Request with headers access for handler's actor_from_http."""
    from starlette.requests import Request

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/learning/releases/rc-1/publish",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 8000),
        "server": ("127.0.0.1", 8000),
        "app": None,
    }
    return Request(scope, _receive)


def test_canary_block_approval_marks_candidate_blocked_and_prevents_publish(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        store = get_execution_store()
        client.get("/api/core/permissions/stats")  # ensure lifespan init

        now = time.time()
        # Seed a release candidate
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "rc-1",
                "kind": "release_candidate",
                "target_type": "agent",
                "target_id": "a1",
                "version": "rc-1",
                "status": "draft",
                "payload": {"artifact_ids": [], "summary": "x"},
                "metadata": {},
                "created_at": now,
            },
        )

        # Seed a canary block approval request (created by canary_web in real flow)
        anyio.run(
            store.upsert_approval_request,
            {
                "request_id": "apr-1",
                "user_id": "system",
                "operation": "canary:block_release_candidate",
                "details": "canary block: P0",
                "rule_id": "canary_block",
                "rule_type": "sensitive_operation",
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "metadata": {"candidate_id": "rc-1", "project_id": "demo"},
                "result": {},
                "tenant_id": "demo",
                "actor_id": "system",
                "actor_role": "system",
                "session_id": "default",
                "run_id": "run-1",
            },
        )

        # The publish HTTP endpoint now lives in aiPlat-platform
        # (apps/learning/api/learning_releases.py → /api/platform/apps/learning/releases/...),
        # which is installed as an editable package in CI. Call the handler directly so the
        # canary-block gate logic is exercised without depending on the platform app lifespan.
        from apps.learning.api.learning_releases import publish_release_candidate

        async def _publish(user_id: str, require_approval: bool = False):
            try:
                await publish_release_candidate(
                    candidate_id="rc-1",
                    request={"user_id": user_id, "require_approval": require_approval},
                    http_request=_make_request(),
                )
                return 200
            except Exception as e:  # noqa: BLE001
                return int(getattr(e, "status_code", 500) or 500)

        # Publishing should be blocked even while pending
        assert anyio.run(_publish, "u1", False) == 409

        # Approve the block -> should mark candidate metadata.blocked=true.
        # The on_approved callback spawns an asyncio task, so approve + wait must
        # run inside the SAME event loop (anyio.run creates a fresh loop per call,
        # and a task created on a loop that is then closed never completes).
        from core.harness.infrastructure.approval import ApprovalManager
        from core.api.core_facade import get_kernel_runtime

        async def _approve_and_wait():
            rt = get_kernel_runtime()
            am = getattr(rt, "approval_manager", None) or ApprovalManager(execution_store=store)
            await am.approve("apr-1", approved_by="admin", comments="ack")
            await anyio.sleep(0.2)
            rc = await store.get_learning_artifact("rc-1")
            return rc

        rc = anyio.run(_approve_and_wait)
        assert rc["metadata"].get("blocked") is True
        assert rc["metadata"].get("blocked_via") == "canary"

        # Publishing should remain blocked after approval (approval means "approve blocking")
        assert anyio.run(_publish, "u1", False) == 409
