import time

import pytest
from unittest.mock import AsyncMock


class CaptureModel:
    def __init__(self):
        self.last_messages = None

    async def generate(self, messages):
        self.last_messages = messages
        return type("R", (), {"content": "ok"})


class PromptingAgent:
    def __init__(self, model):
        self._model = model

    async def execute(self, context):
        from core.harness.interfaces.agent import AgentResult
        from core.harness.syscalls.llm import sys_llm_generate

        # This should be patched by prompt_revision when enabled
        await sys_llm_generate(self._model, "BASE_PROMPT", trace_context={"trace_id": "t1", "run_id": "r1"})
        return AgentResult(success=True, output={"ok": True}, metadata={})


class DummyAgentInfo:
    def __init__(self):
        self.config = {"model": "gpt-4"}
        self.tools = []
        self.skills = []


@pytest.mark.asyncio
async def test_phase68_prompt_revision_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_ENABLE_LEARNING_APPLIER", "true")
    monkeypatch.setenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true")
    monkeypatch.setenv("AIPLAT_APPLY_PROMPT_REVISIONS", "true")

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

    # Seed prompt_revision + published release_candidate referencing it
    now = time.time()
    await store.upsert_learning_artifact(
        {
            "artifact_id": "pr-1",
            "kind": "prompt_revision",
            "target_type": "agent",
            "target_id": "a1",
            "version": "pr-1",
            "status": "published",
            "trace_id": None,
            "run_id": None,
            "payload": {"patch": {"prepend": "PRE", "append": "POST"}},
            "metadata": {},
            "created_at": now,
        }
    )
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
            "payload": {"artifact_ids": ["pr-1"], "summary": "apply prompt"},
            "metadata": {},
            "created_at": now + 1,
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

    model = CaptureModel()
    agent = PromptingAgent(model)

    import core.apps.agents as agents_mod

    monkeypatch.setattr(agents_mod, "get_agent_registry", lambda: {"a1": agent})

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

    # Ensure prompt was patched
    assert model.last_messages is not None
    assert isinstance(model.last_messages, list)
    content = model.last_messages[0]["content"]
    assert content.startswith("PRE\n")
    assert content.endswith("\nPOST")

