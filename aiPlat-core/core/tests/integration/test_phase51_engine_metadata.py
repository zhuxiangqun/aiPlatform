import pytest
from unittest.mock import AsyncMock


class DummyAgent:
    async def execute(self, context):
        from core.harness.interfaces.agent import AgentResult

        return AgentResult(success=True, output={"ok": True}, metadata={"agent_meta": 1})


class DummyAgentInfo:
    def __init__(self):
        self.config = {"model": "gpt-4"}
        self.tools = []
        self.skills = []


@pytest.mark.asyncio
async def test_phase51_engine_metadata_persisted(tmp_path, monkeypatch):
    """
    Phase 5.1 acceptance:
    - HarnessIntegration routes agent via EngineRouter (loop engine, behavior-preserving)
    - engine/explain/fallback_chain/fallback_trace are persisted into agent_executions.metadata_json
    """
    # ExecutionStore for persistence
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

    # Wire runtime with a mocked agent manager
    agent_manager = AsyncMock()
    agent_manager.get_agent = AsyncMock(return_value=DummyAgentInfo())

    runtime = KernelRuntime(
        agent_manager=agent_manager,
        execution_store=store,
        trace_service=trace_service,
        approval_manager=ApprovalManager(execution_store=store),
    )

    # Patch agent registry to return our dummy agent
    import core.apps.agents as agents_mod

    monkeypatch.setattr(agents_mod, "get_agent_registry", lambda: {"a1": DummyAgent()})

    # Grant permission for agent execute
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
    assert meta.get("engine") == "loop"
    assert isinstance(meta.get("engine_explain"), str) and meta.get("engine_explain")
    assert meta.get("fallback_chain") == ["loop"]
    assert isinstance(meta.get("fallback_trace"), list) and len(meta.get("fallback_trace")) >= 1
    assert meta["fallback_trace"][0].get("engine") == "loop"

