import time

import pytest


class CaptureModel:
    def __init__(self):
        self.last_messages = None

    async def generate(self, messages):
        self.last_messages = messages
        return type("R", (), {"content": "ok"})


@pytest.mark.asyncio
async def test_phase613_trace_span_has_prompt_revision_attrs(tmp_path, monkeypatch):
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
    # prompt revisions and published release
    await store.upsert_learning_artifact(
        {
            "artifact_id": "pr-1",
            "kind": "prompt_revision",
            "target_type": "agent",
            "target_id": "a1",
            "version": "pr-1",
            "status": "published",
            "payload": {"patch": {"prepend": "P1"}},
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
            "payload": {"patch": {"prepend": "P2"}},
            "metadata": {"exclusive_group": "g1", "priority": 0},
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
            "payload": {"artifact_ids": ["pr-1", "pr-2"], "summary": "span"},
            "metadata": {},
            "created_at": now + 2,
        }
    )

    trace = await trace_service.start_trace("t", attributes={"k": "v"})
    token = set_active_release_context(
        ActiveReleaseContext(target_type="agent", target_id="a1", candidate_id="rc-1", version="rc-1", summary="span")
    )
    model = CaptureModel()
    try:
        await sys_llm_generate(model, "BASE", trace_context={"trace_id": trace.trace_id, "run_id": "r1"})
    finally:
        reset_active_release_context(token)
        await trace_service.end_trace(trace.trace_id)

    persisted = await store.get_trace(trace.trace_id, include_spans=True)
    assert persisted is not None
    spans = persisted.get("spans") or []
    s = next(sp for sp in spans if sp.get("name") == "sys.llm.generate")
    attrs = s.get("attributes") or {}
    assert attrs.get("active_release_candidate_id") == "rc-1"
    assert attrs.get("active_release_version") == "rc-1"
    assert attrs.get("prompt_revision_strict") is True
    assert "pr-1" in (attrs.get("applied_prompt_revision_ids") or [])
    assert "pr-2" in (attrs.get("ignored_prompt_revision_ids") or [])

