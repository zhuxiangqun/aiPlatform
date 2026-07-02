"""
RunState persistence & restore — extracted from loop.py state management cluster.

Handles: persist, todo-done markers, load, restate.
"""
from typing import Any, Dict, Optional
import os, time, logging

from ...interfaces.loop import LoopState
from ...kernel.runtime import get_kernel_runtime
from ...restatement.run_state import (
    default_run_state,
    format_run_state_for_prompt,
    normalize_run_state,
    restate_next_step,
    set_todo_status,
)

async def persist_run_state(state: LoopState, **kwargs):
    """Original: _persist_run_state (loop.py:705)"""
    runtime = get_kernel_runtime()
    store = getattr(runtime, "execution_store", None) if runtime else None
    if store is None:
        return
    rs = state.context.get("run_state")
    if not isinstance(rs, dict):
        return
    try:
        from core.learning.manager import LearningManager
        from core.learning.types import LearningArtifactKind

        mgr = LearningManager(execution_store=store)
        run_id = state.context.get("_run_id") or state.context.get("run_id")
        await mgr.create_artifact(
            kind=LearningArtifactKind.RUN_STATE,
            target_type="run",
            target_id=str(run_id),
            version=f"run_state:{int(time.time())}",
            status="draft",
            payload=rs,
            metadata={"source": source, **(extra or {}), "locked": bool(rs.get("locked"))},
            trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
            run_id=str(run_id),
        )
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    try:
        if hasattr(store, "append_run_event"):
            await store.append_run_event(
                run_id=str(state.context.get("_run_id") or state.context.get("run_id")),
                event_type="run_state",
                trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                tenant_id=state.context.get("tenant_id"),
                payload={"source": source, **(extra or {})},
            )
    except Exception as e:
        logging.warning(str(e), exc_info=True)


async def apply_todo_done_markers(state: LoopState, **kwargs):
    """Original: _apply_todo_done_markers (loop.py:744)"""
    if os.getenv("AIPLAT_RUN_STATE_PARSE_TODO_DONE", "true").lower() not in ("1", "true", "yes", "y"):
        return
    done_ids = []
    for token in str(text or "").split():
        if token.startswith("TODO_DONE:"):
            done_ids.append(token.split("TODO_DONE:", 1)[1].strip())
    if not done_ids:
        return
    rs = state.context.get("run_state")
    if not isinstance(rs, dict):
        return
    for tid in done_ids[:20]:
        rs = set_todo_status(rs, todo_id=tid, status="completed", source=f"todo_done_marker:{source}")
    state.context["run_state"] = rs
    await self._persist_run_state(state, source=f"todo_done_marker:{source}", extra={"done_ids": done_ids[:20]})


async def load_run_state_for_prompt(state: LoopState, **kwargs):
    """Original: _load_run_state_for_prompt (loop.py:1077)"""
    """
    Load latest run_state artifact (if any) into state.context["run_state"].
    """
    run_id = state.context.get("_run_id") or state.context.get("run_id")
    if not run_id:
        return
    if isinstance(state.context.get("run_state"), dict):
        return
    runtime = get_kernel_runtime()
    store = getattr(runtime, "execution_store", None) if runtime else None
    if store is None or not hasattr(store, "list_learning_artifacts"):
        state.context["run_state"] = default_run_state(run_id=str(run_id), task=str(state.context.get("task") or ""))
        return
    try:
        res = await store.list_learning_artifacts(target_type="run", target_id=str(run_id), kind="run_state", limit=10, offset=0)
        items = res.get("items") if isinstance(res, dict) else None
        if isinstance(items, list) and items:
            items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
            payload = (items2[0] or {}).get("payload") if isinstance(items2[0], dict) else {}
            rs = normalize_run_state(payload, run_id=str(run_id))
            if not str(rs.get("task") or "").strip():
                rs["task"] = str(state.context.get("task") or "")
            state.context["run_state"] = rs
            state.context["_run_state_artifact_id"] = (items2[0] or {}).get("artifact_id")
            return
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    state.context["run_state"] = default_run_state(run_id=str(run_id), task=str(state.context.get("task") or ""))


async def restate_and_persist_run_state(state: LoopState, **kwargs):
    """Original: _maybe_restate_and_persist_run_state (loop.py:1107)"""
    """
    Periodically refresh run_state.next_step and persist (debounced).
    - restate: append run_event every N steps
    - persist: write learning artifact every M steps
    """
    run_id = state.context.get("_run_id") or state.context.get("run_id")
    if not run_id:
        return
    rs = state.context.get("run_state")
    if not isinstance(rs, dict):
        return
    if os.getenv("AIPLAT_ENABLE_RUN_STATE", "true").lower() not in ("1", "true", "yes", "y"):
        return

    try:
        restate_n = int(os.getenv("AIPLAT_RUN_STATE_RESTATE_EVERY_N_STEPS", "5"))
    except Exception:
        restate_n = 5
    try:
        persist_n = int(os.getenv("AIPLAT_RUN_STATE_PERSIST_EVERY_N_STEPS", "20"))
    except Exception:
        persist_n = 20

    step_count = int(getattr(state, "step_count", 0) or 0)
    if step_count <= 0:
        return

    # Always keep task filled
    if not str(rs.get("task") or "").strip():
        rs["task"] = str(state.context.get("task") or "")

    # Restate (cheap)
    if restate_n > 0 and (step_count % restate_n == 0):
        rs2 = restate_next_step(rs, step_count=step_count, last_error=state.context.get("error"))
        state.context["run_state"] = rs2
        # run event
        try:
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            if store is not None and hasattr(store, "append_run_event"):
                await store.append_run_event(
                    run_id=str(run_id),
                    event_type="run_state",
                    trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                    tenant_id=state.context.get("tenant_id"),
                    payload={"source": "loop", "step_count": step_count, "locked": bool(rs2.get("locked")), "next_step": rs2.get("next_step")},
                )
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # Persist (debounced)
    if persist_n > 0 and (step_count % persist_n == 0):
        try:
            if bool(state.context.get("run_state", {}).get("locked")):
                return
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            if store is None:
                return
            from core.learning.manager import LearningManager
            from core.learning.types import LearningArtifactKind

            mgr = LearningManager(execution_store=store)
            await mgr.create_artifact(
                kind=LearningArtifactKind.RUN_STATE,
                target_type="run",
                target_id=str(run_id),
                version=f"run_state:{int(time.time())}",
                status="draft",
                payload=state.context.get("run_state"),
                metadata={"source": "loop", "step_count": step_count, "locked": bool(state.context.get("run_state", {}).get("locked"))},
                trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                run_id=str(run_id),
            )
        except Exception as e:
            logging.warning(str(e), exc_info=True)
