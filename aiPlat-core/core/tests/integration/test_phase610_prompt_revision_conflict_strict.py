import time

import pytest


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

        await sys_llm_generate(self._model, "BASE", trace_context={"trace_id": "t1", "run_id": "r1"})
        return AgentResult(success=True, output={"ok": True}, metadata={})


class DummyAgentInfo:
    def __init__(self):
        self.config = {"model": "gpt-4"}
        self.tools = []
        self.skills = []


@pytest.mark.asyncio
async def test_phase610_prompt_revision_conflict_strict_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true")
    monkeypatch.setenv("AIPLAT_APPLY_PROMPT_REVISIONS", "true")
    monkeypatch.setenv("AIPLAT_PROMPT_REVISION_STRICT", "true")

    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.services.trace_service import TraceService
    from core.harness.integration import KernelRuntime
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.harness.kernel.runtime import set_kernel_runtime
    from core.harness.kernel.execution_context import ActiveReleaseContext, set_active_release_context, reset_active_release_context
    from core.harness.syscalls.llm import sys_llm_generate

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    trace_service = TraceService(execution_store=store)

    runtime = KernelRuntime(execution_store=store, trace_service=trace_service, approval_manager=ApprovalManager(execution_store=store))
    set_kernel_runtime(runtime)

    now = time.time()
    # Two prompt revisions in same exclusive_group; strict mode should keep first only.
    await store.upsert_learning_artifact(
        {
            "artifact_id": "pr-1",
            "kind": "prompt_revision",
            "target_type": "agent",
            "target_id": "a1",
            "version": "pr-1",
            "status": "published",
            "payload": {"patch": {"prepend": "P1"}},
            "metadata": {"exclusive_group": "g1"},
            "created_at": now,
        }
    )
    await store.upsert_learning_artifact(
        {
            "artifact_id": "pr-2",
            "kind": "prompt_revision",
            "target_type": "agent",
            "target_id": "a1",
            "version": "pr-2",
            "status": "published",
            "payload": {"patch": {"prepend": "P2"}},
            "metadata": {"exclusive_group": "g1"},
            "created_at": now + 1,
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
            "payload": {"artifact_ids": ["pr-1", "pr-2"], "summary": "conflict"},
            "metadata": {},
            "created_at": now + 2,
        }
    )

    # Sanity: applier resolves patch
    from core.learning.apply import LearningApplier

    resolved = await LearningApplier(store).resolve_prompt_revision_patch(target_type="agent", target_id="a1")
    assert resolved.get("patch", {}).get("prepend") == "P1"

    model = CaptureModel()
    token = set_active_release_context(
        ActiveReleaseContext(target_type="agent", target_id="a1", candidate_id="rc-1", version="rc-1", summary="conflict")
    )
    try:
        await sys_llm_generate(model, "BASE", trace_context={"trace_id": "t1", "run_id": "r1"})
    finally:
        reset_active_release_context(token)

    assert isinstance(model.last_messages, list)
    # Only P1 should be applied; P2 ignored.
    assert model.last_messages[0]["content"].startswith("P1\nBASE")
    assert "P2" not in model.last_messages[0]["content"]

    evs = await store.list_syscall_events(run_id="r1", limit=10, offset=0)
    assert evs["total"] >= 1
    latest = evs["items"][0]
    result = latest.get("result") or {}
    assert result.get("ignored_prompt_revision_ids") == ["pr-2"]
    assert isinstance(result.get("prompt_revision_conflicts"), list) and result["prompt_revision_conflicts"]
