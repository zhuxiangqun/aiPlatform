import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_learning_applier_rollout_overrides_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_ENABLE_RELEASE_ROLLOUTS", "true")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        _ = client.get("/api/core/health")
        store = getattr(server, "_execution_store", None)
        assert store is not None

        async def _run():
            await store.init()

            # Two published candidates for the same target; latest created_at = stable
            await store.upsert_learning_artifact(
                {
                    "artifact_id": "rc_stable",
                    "kind": "release_candidate",
                    "target_type": "agent",
                    "target_id": "a1",
                    "version": "v2",
                    "status": "published",
                    "payload": {"summary": "stable"},
                    "metadata": {},
                    "created_at": 2000.0,
                }
            )
            await store.upsert_learning_artifact(
                {
                    "artifact_id": "rc_canary",
                    "kind": "release_candidate",
                    "target_type": "agent",
                    "target_id": "a1",
                    "version": "v1",
                    "status": "published",
                    "payload": {"summary": "canary"},
                    "metadata": {},
                    "created_at": 1000.0,
                }
            )

            # Rollout forces canary for this tenant/target (mode=all to avoid hash flakiness)
            await store.upsert_release_rollout(
                tenant_id="t_demo",
                target_type="agent",
                target_id="a1",
                candidate_id="rc_canary",
                mode="all",
                enabled=True,
            )

            from core.harness.kernel.execution_context import ActiveRequestContext, set_active_request_context
            from core.learning.apply import LearningApplier

            tok = set_active_request_context(
                ActiveRequestContext(user_id="u1", session_id="s1", tenant_id="t_demo", actor_id="u1", actor_role="developer")
            )
            try:
                ar = await LearningApplier(store).resolve_active_release(target_type="agent", target_id="a1")
                assert ar is not None
                assert ar.candidate_id == "rc_canary"
            finally:
                try:
                    tok.reset()
                except Exception:
                    pass

        anyio.run(_run)
