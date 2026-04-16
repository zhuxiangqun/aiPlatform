import time

import pytest
from unittest.mock import AsyncMock


class DummyAgent:
    async def execute(self, context):
        from core.harness.interfaces.agent import AgentResult

        return AgentResult(success=True, output={"ok": True}, metadata={})


class DummyAgentInfo:
    def __init__(self):
        self.config = {"model": "gpt-4"}
        self.tools = []
        self.skills = []


@pytest.mark.asyncio
async def test_phase67_active_release_injected(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_ENABLE_LEARNING_APPLIER", "true")

    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.services.trace_service import TraceService
    from core.harness.integration import HarnessIntegration, HarnessConfig, KernelRuntime
    from core.harness.kernel.types import ExecutionRequest
    from core.apps.tools.permission import get_permission_manager, Permission
    from core.harness.infrastructure.approval.manager import ApprovalManager

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    trace_service = TraceService(execution_store=store)

    # Seed a published release_candidate for agent a1
    now = time.time()
    await store.upsert_learning_artifact(
        {
            "artifact_id": "rc-1",
            "kind": "release_candidate",
            "target_type": "agent",
            "target_id": "a1",
            "version": "rc-1",
            "status": "published",
            "trace_id": None,
            "run_id": None,
            "payload": {"artifact_ids": [], "summary": "test"},
            "metadata": {},
            "created_at": now,
        }
    )

    agent_manager = AsyncMock()
    agent_manager.get_agent = AsyncMock(return_value=DummyAgentInfo())

    runtime = KernelRuntime(
        agent_manager=agent_manager,
        execution_store=store,
        trace_service=trace_service,
        approval_manager=ApprovalManager(execution_store=store),
    )

    import core.apps.agents as agents_mod

    monkeypatch.setattr(agents_mod, "get_agent_registry", lambda: {"a1": DummyAgent()})

    perm_mgr = get_permission_manager()
    perm_mgr.grant_permission("u1", "a1", Permission.EXECUTE)

    harness = HarnessIntegration.initialize(HarnessConfig(enable_observability=False, enable_feedback_loops=False))
    harness.attach_runtime(runtime)

    res = await harness.execute(
        ExecutionRequest(
            kind="agent",
            target_id="a1",
            user_id="u1",
            session_id="s1",
            payload={"messages": [{"role": "user", "content": "hi"}], "session_id": "s1", "context": {}},
        )
    )
    assert res.ok is True
    execution_id = res.payload.get("execution_id")
    assert execution_id

    rec = await store.get_agent_execution(execution_id)
    assert rec is not None
    meta = rec.get("metadata") or {}
    ar = meta.get("active_release")
    assert isinstance(ar, dict)
    assert ar.get("candidate_id") == "rc-1"
    assert ar.get("version") == "rc-1"

