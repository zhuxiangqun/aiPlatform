import time

import pytest


class CaptureModel:
    def __init__(self):
        self.last_messages = None

    async def generate(self, messages):
        self.last_messages = messages
        return type("R", (), {"content": "ok"})


@pytest.mark.asyncio
async def test_phase611_prompt_revision_priority_strict_selects_highest(tmp_path, monkeypatch):
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
    # Same exclusive_group, but pr-2 has higher priority and should win in strict mode.
    await store.upsert_learning_artifact(
        {
            "artifact_id": "pr-1",
            "kind": "prompt_revision",
            "target_type": "agent",
            "target_id": "a1",
            "version": "pr-1",
            "status": "published",
            "payload": {"patch": {"prepend": "LOW"}},
            "metadata": {"exclusive_group": "g1", "priority": 1},
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
            "payload": {"patch": {"prepend": "HIGH"}},
            "metadata": {"exclusive_group": "g1", "priority": 10},
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
            "payload": {"artifact_ids": ["pr-1", "pr-2"], "summary": "priority"},
            "metadata": {},
            "created_at": now + 2,
        }
    )

    model = CaptureModel()
    token = set_active_release_context(
        ActiveReleaseContext(target_type="agent", target_id="a1", candidate_id="rc-1", version="rc-1", summary="priority")
    )
    try:
        await sys_llm_generate(model, "BASE", trace_context={"trace_id": "t1", "run_id": "r1"})
    finally:
        reset_active_release_context(token)

    assert isinstance(model.last_messages, list)
    assert model.last_messages[0]["content"].startswith("HIGH\nBASE")

    evs = await store.list_syscall_events(run_id="r1", limit=10, offset=0)
    latest = evs["items"][0]
    result = latest.get("result") or {}
    assert result.get("applied_prompt_revision_ids")[0] == "pr-2"
    assert "pr-1" in (result.get("ignored_prompt_revision_ids") or [])

