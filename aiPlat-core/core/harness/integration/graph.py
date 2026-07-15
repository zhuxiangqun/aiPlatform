"""Auto-extracted from integration.py — 2026-07-13"""
from __future__ import annotations


async def _execute_graph_impl(self, req: ExecutionRequest) -> ExecutionResult:
    # Phase-1: only support compiled_react execution via internal compiled graph.
    from core.harness.kernel.types import ExecutionResult

    runtime = self._runtime
    if runtime is None or runtime.execution_store is None:
        return self._fail(code="NOT_INITIALIZED", message="ExecutionStore not initialized", http_status=503)

    payload = req.payload or {}
    messages = payload.get("messages") or []
    context = payload.get("context") or {}
    max_steps = int(payload.get("max_steps", 10) or 10)
    checkpoint_interval = int(payload.get("checkpoint_interval", 1) or 1)

    class _DefaultModel:
        async def generate(self, prompt):
            return type("R", (), {"content": "DONE"})

    from core.harness.execution.langgraph.compiled_graphs import create_compiled_react_graph
    from core.harness.execution.langgraph.core import GraphConfig

    graph_run_id = new_prefixed_id("run")

    trace_id = None
    if runtime.trace_service:
        try:
            t = await runtime.trace_service.start_trace(
                name=f"graph:{req.target_id}",
                attributes={"graph_name": req.target_id, "graph_run_id": graph_run_id, "source": "graph"},
            )
            trace_id = t.trace_id
        except Exception:
            trace_id = None

    graph = create_compiled_react_graph(model=_DefaultModel(), tools=[], max_steps=max_steps)
    initial_state = {
        "messages": messages,
        "context": context,
        "step_count": 0,
        "max_steps": max_steps,
        "metadata": {"graph_run_id": graph_run_id, "trace_id": trace_id},
    }
    try:
        final_state = await graph.execute(
            initial_state,
            config=GraphConfig(
                max_steps=max_steps,
                enable_checkpoints=True,
                checkpoint_interval=checkpoint_interval,
                enable_callbacks=True,
            ),
        )
    finally:
        if runtime.trace_service and trace_id:
            try:
                from core.services.trace_service import SpanStatus

                await runtime.trace_service.end_trace(trace_id, status=SpanStatus.SUCCESS)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    run_id = (final_state.get("metadata") or {}).get("graph_run_id")
    return ExecutionResult(ok=True, payload={"run_id": run_id, "final_state": final_state}, trace_id=trace_id, run_id=run_id)

async def _execute_smoke_e2e_impl(self, req: ExecutionRequest) -> ExecutionResult:
    """Production-grade full-chain smoke (for CI & ops)."""
    from core.harness.kernel.types import ExecutionResult

    runtime = self._runtime
    if runtime is None or runtime.execution_store is None:
        return self._fail(code="NOT_INITIALIZED", message="ExecutionStore not initialized", http_status=503)

    payload = req.payload if isinstance(req.payload, dict) else {}
    run_id = str(getattr(req, "run_id", None) or "") or new_prefixed_id("run")

    trace_id = None
    if runtime.trace_service:
        try:
            trace = await runtime.trace_service.start_trace(
                name="smoke:e2e",
                attributes={
                    "run_id": run_id,
                    "kind": "smoke_e2e",
                    "actor_id": payload.get("actor_id") or req.user_id,
                    "tenant_id": payload.get("tenant_id"),
                },
            )
            trace_id = trace.trace_id
        except Exception:
            trace_id = None

    # run_start
    try:
        exec_backend = None
        try:
            exec_backend = await _resolve_exec_backend()
        except Exception:
            exec_backend = None
        await runtime.execution_store.append_run_event(
            run_id=run_id,
            event_type="run_start",
            trace_id=trace_id,
            tenant_id=str(payload.get("tenant_id")) if payload.get("tenant_id") else None,
            payload={
                "kind": "smoke_e2e",
                "status": "running",
                "exec_backend": exec_backend,
                "request_payload": self._redact_request_payload(payload),
            },
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    try:
        from core.harness.smoke.e2e import run_smoke_e2e

        res = await run_smoke_e2e(payload=payload, execution_store=runtime.execution_store)
        status = "completed" if res.get("ok") else "failed"
        try:
            await runtime.execution_store.append_run_event(
                run_id=run_id,
                event_type="run_end",
                trace_id=trace_id,
                tenant_id=str(payload.get("tenant_id")) if payload.get("tenant_id") else None,
                payload={"kind": "smoke_e2e", "status": status},
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return ExecutionResult(
            ok=True,
            payload={"run_id": run_id, "status": status, **res},
            trace_id=trace_id,
            run_id=run_id,
        )
    except Exception as e:
        try:
            await runtime.execution_store.append_run_event(
                run_id=run_id,
                event_type="run_end",
                trace_id=trace_id,
                tenant_id=str(payload.get("tenant_id")) if payload.get("tenant_id") else None,
                payload={"kind": "smoke_e2e", "status": "failed", "error": str(e)},
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return self._fail(code="EXCEPTION", message=str(e), http_status=500, trace_id=trace_id, run_id=run_id)
