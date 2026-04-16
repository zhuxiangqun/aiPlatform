import sqlite3

import pytest


class DummyApprovalTool:
    name = "dummy_approval_tool"

    async def execute(self, params):
        from core.harness.interfaces.tool import ToolResult

        return ToolResult(success=True, output={"ok": True, "params": params})


@pytest.mark.asyncio
async def test_phase35_approval_required_then_resume_span_link(tmp_path, monkeypatch):
    """
    Phase 3.5 acceptance:
    - First sys_tool_call returns approval_required (PolicyGate enforces approval)
    - After approving, a resumed sys_tool_call with _approval_request_id succeeds
    - Both syscall_events rows have span_id and can join spans table
    """
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "true")

    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.services.trace_service import TraceService
    from core.harness.integration import KernelRuntime
    from core.harness.kernel.runtime import set_kernel_runtime
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.harness.infrastructure.approval.types import ApprovalRule, RuleType
    from core.apps.tools.permission import get_permission_manager, Permission
    from core.harness.syscalls.tool import sys_tool_call

    # Init persistence + tracing
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    trace_service = TraceService(execution_store=store)

    # Init approval manager with a rule that matches tool:dummy_approval_tool
    approval_mgr = ApprovalManager(execution_store=store)
    approval_mgr.register_rule(
        ApprovalRule(
            rule_id="test_sensitive_tool",
            rule_type=RuleType.SENSITIVE_OPERATION,
            name="测试敏感工具审批",
            description="对 dummy_approval_tool 触发审批",
            priority=1,
            metadata={"sensitive_operations": ["tool:dummy_approval_tool"]},
        )
    )

    runtime = KernelRuntime(
        execution_store=store,
        trace_service=trace_service,
        approval_manager=approval_mgr,
    )
    set_kernel_runtime(runtime)

    # Allow tool execution
    perm_mgr = get_permission_manager()
    perm_mgr.grant_permission("u1", "dummy_approval_tool", Permission.EXECUTE)

    # Create a trace and attempt tool call: should require approval
    trace = await trace_service.start_trace(name="t-approval", attributes={"test": True})
    trace_id = trace.trace_id
    trace_ctx = {"trace_id": trace_id, "run_id": "run-approval-1"}

    tool = DummyApprovalTool()
    r1 = await sys_tool_call(tool, {"x": 1}, user_id="u1", session_id="s1", trace_context=trace_ctx)
    assert getattr(r1, "error", None) == "approval_required"
    approval_request_id = (getattr(r1, "metadata", {}) or {}).get("approval_request_id")
    assert approval_request_id

    # Approve and resume (attach _approval_request_id)
    await approval_mgr.approve(str(approval_request_id), approved_by="tester", comments="ok")
    r2 = await sys_tool_call(
        tool,
        {"x": 2, "_approval_request_id": str(approval_request_id)},
        user_id="u1",
        session_id="s1",
        trace_context=trace_ctx,
    )
    assert bool(getattr(r2, "success", False)) is True

    await trace_service.end_trace(trace_id)

    # Validate persistence: syscall_events have span_id and approval_request_id and join spans
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT trace_id, span_id, status, approval_request_id
            FROM syscall_events
            WHERE trace_id=?
            ORDER BY created_at ASC
            """,
            (trace_id,),
        ).fetchall()
        assert len(rows) >= 2
        assert all(r["span_id"] is not None and str(r["span_id"]) != "" for r in rows)
        assert set(r["approval_request_id"] for r in rows if r["approval_request_id"]) == {str(approval_request_id)}
        assert any(r["status"] == "approval_required" for r in rows)
        assert any(r["status"] == "success" for r in rows)

        missing_join = conn.execute(
            """
            SELECT COUNT(1) AS c
            FROM syscall_events e
            LEFT JOIN spans s ON s.span_id = e.span_id
            WHERE e.trace_id=? AND s.span_id IS NULL;
            """,
            (trace_id,),
        ).fetchone()
        assert int(missing_join["c"]) == 0
    finally:
        conn.close()

