import json

import pytest
from unittest.mock import AsyncMock


class DummyModel:
    async def generate(self, messages):
        # Return a strict JSON plan the orchestrator can parse
        plan = {
            "explain": "测试计划",
            "steps": [
                {"step": 1, "kind": "instruction", "action": "第一步"},
                {"step": 2, "kind": "tool", "action": "dummy_tool", "args": {"x": 1}},
            ],
        }
        return type("R", (), {"content": json.dumps(plan, ensure_ascii=False)})


class DummyAgent:
    def __init__(self):
        self._model = DummyModel()

    async def execute(self, context):
        from core.harness.interfaces.agent import AgentResult

        return AgentResult(success=True, output={"ok": True}, metadata={})


class DummyAgentInfo:
    def __init__(self):
        self.config = {"model": "gpt-4"}
        self.tools = []
        self.skills = []


@pytest.mark.asyncio
async def test_phase52_orchestrator_plan_persisted(tmp_path, monkeypatch):
    """
    Phase 5.2 acceptance:
    - Orchestrator (plan-only) runs behind env flag
    - orchestrator_plan is persisted into agent_executions.metadata_json
    - execution behavior remains OK
    """
    monkeypatch.setenv("AIPLAT_ENABLE_ORCHESTRATOR", "true")

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
    plan = meta.get("orchestrator_plan")
    assert isinstance(plan, dict)
    assert plan.get("version") == "5.2"
    assert isinstance(plan.get("steps"), list) and len(plan["steps"]) >= 1

