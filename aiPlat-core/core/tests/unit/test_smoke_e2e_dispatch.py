import pytest


@pytest.mark.anyio
async def test_smoke_e2e_dispatch(monkeypatch):
    # Ensure we can execute kind=smoke_e2e without actually doing network calls.
    from core.harness.integration import HarnessIntegration, KernelRuntime
    from core.harness.kernel.types import ExecutionRequest

    class FakeStore:
        async def append_run_event(self, *, run_id: str, event_type: str, payload=None, trace_id=None, tenant_id=None):
            return 1

        async def list_audit_logs(self, **kwargs):
            return {"items": [], "total": 0, "limit": 10, "offset": 0}

    harness = HarnessIntegration.initialize()
    harness.attach_runtime(KernelRuntime(execution_store=FakeStore(), trace_service=None, agent_manager=None, skill_manager=None))

    async def fake_run_smoke_e2e(*, payload, execution_store=None):
        return {"ok": True, "evidence": {"steps": []}}

    # patch runner
    import core.harness.smoke.e2e as smoke_mod

    monkeypatch.setattr(smoke_mod, "run_smoke_e2e", fake_run_smoke_e2e)

    req = ExecutionRequest(kind="smoke_e2e", target_id="smoke_e2e", payload={"tenant_id": "t1"}, user_id="admin", session_id="s1")
    res = await harness.execute(req)
    assert res.ok is True
    assert res.payload["ok"] is True
