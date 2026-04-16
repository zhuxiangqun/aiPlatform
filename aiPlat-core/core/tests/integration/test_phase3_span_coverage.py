import sqlite3
import time

import pytest


class DummyModel:
    async def generate(self, messages):
        # Minimal response object with expected attributes
        return type("R", (), {"content": "OK", "model": "dummy", "usage": {}})


class DummyTool:
    name = "dummy_tool"

    async def execute(self, params):
        from core.harness.interfaces.tool import ToolResult

        return ToolResult(success=True, output={"echo": params})


class DummySkill:
    name = "dummy_skill"

    async def execute(self, context, params):
        from core.harness.interfaces.skill import SkillResult

        return SkillResult(success=True, output={"vars": params})


@pytest.mark.asyncio
async def test_phase3_syscall_span_coverage(tmp_path, monkeypatch):
    """
    Phase 3 acceptance: syscalls must create spans and syscall_events must link to spans.
    """
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.services.trace_service import TraceService
    from core.harness.integration import KernelRuntime
    from core.harness.kernel.runtime import set_kernel_runtime
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.apps.tools.permission import get_permission_manager, Permission
    from core.harness.syscalls.llm import sys_llm_generate
    from core.harness.syscalls.tool import sys_tool_call
    from core.harness.syscalls.skill import sys_skill_call
    from core.harness.interfaces.skill import SkillContext

    # Init persistence
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    trace_service = TraceService(execution_store=store)

    # Init runtime for syscalls
    runtime = KernelRuntime(
        execution_store=store,
        trace_service=trace_service,
        approval_manager=ApprovalManager(execution_store=store),
    )
    set_kernel_runtime(runtime)

    # Allow tool execution
    perm_mgr = get_permission_manager()
    perm_mgr.grant_permission("u1", "dummy_tool", Permission.EXECUTE)

    # Create a trace and run a few syscalls under it
    trace = await trace_service.start_trace(name="t", attributes={"test": True})
    trace_id = trace.trace_id
    run_id = "run-1"
    trace_ctx = {"trace_id": trace_id, "run_id": run_id}

    await sys_llm_generate(DummyModel(), [{"role": "user", "content": "hi"}], trace_context=trace_ctx)
    await sys_tool_call(DummyTool(), {"x": 1}, user_id="u1", session_id="s1", trace_context=trace_ctx)
    await sys_skill_call(
        DummySkill(),
        {"y": 2},
        context=SkillContext(session_id="s1", user_id="u1", variables={"y": 2}),
        user_id="u1",
        session_id="s1",
        trace_context=trace_ctx,
    )

    await trace_service.end_trace(trace_id)

    # Validate: syscall_events have span_id and can join spans
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, trace_id, span_id FROM syscall_events ORDER BY created_at ASC").fetchall()
        assert len(rows) >= 3
        assert all(r["trace_id"] == trace_id for r in rows)
        assert all(r["span_id"] is not None and str(r["span_id"]) != "" for r in rows)

        missing_join = conn.execute(
            """
            SELECT COUNT(1) AS c
            FROM syscall_events e
            LEFT JOIN spans s ON s.span_id = e.span_id
            WHERE s.span_id IS NULL;
            """
        ).fetchone()
        assert int(missing_join["c"]) == 0
    finally:
        conn.close()

