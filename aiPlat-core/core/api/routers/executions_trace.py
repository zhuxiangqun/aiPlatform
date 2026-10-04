from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional, Any, List

from fastapi import APIRouter, Depends, HTTPException

from core.api.core_facade import KernelRuntime  # P0-A2: 经 CoreFacade
from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


def _iso(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.utcfromtimestamp(float(ts)).isoformat()
    except Exception:
        return None


async def _load_execution_record(store: Any, execution_id: str) -> Optional[Dict[str, Any]]:
    """Prefer agent_executions, then skill_executions."""
    try:
        rec = await store.get_agent_execution(execution_id)
        if rec:
            return {"kind": "agent", **rec}
    except Exception:  # noqa: cleanup-best-effort
        pass
    getter = getattr(store, "get_skill_execution", None)
    if callable(getter):
        try:
            rec = await getter(execution_id)
            if rec:
                return {"kind": "skill", **rec}
        except Exception:  # noqa: cleanup-best-effort
            pass
    return None


async def _syscall_spans(store: Any, execution_id: str, trace_id: str) -> List[Dict[str, Any]]:
    from core.harness.utils.diag_spans import syscall_spans
    return await syscall_spans(store, execution_id, trace_id)


async def _run_graph_spans(store: Any, execution_id: str, trace_id: str) -> List[Dict[str, Any]]:
    from core.harness.utils.diag_spans import run_graph_spans
    return await run_graph_spans(store, execution_id, trace_id)


async def _merged_diag_spans(
    store: Any,
    execution_id: str,
    trace_id: str,
    *,
    existing: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    from core.harness.utils.diag_spans import merged_diag_spans
    return await merged_diag_spans(store, execution_id, trace_id, existing=existing)


async def _heal_or_synthesize_trace(
    store: Any,
    execution_id: str,
    trace_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Workspace agents historically wrote agent_executions.trace_id without upsert_trace.
    Heal by upserting a traces row + attaching syscall spans so Links UI can render.
    """
    rec = await _load_execution_record(store, execution_id)
    if not rec:
        return None
    kind = rec.get("kind") or "agent"
    name_key = rec.get("agent_id") or rec.get("skill_name") or execution_id
    start = rec.get("start_time") or rec.get("created_at")
    end = rec.get("end_time")
    status = rec.get("status") or "unknown"
    duration_ms = rec.get("duration_ms")
    try:
        await store.upsert_trace({
            "trace_id": trace_id,
            "name": f"{kind}:{name_key}",
            "status": "completed" if status == "completed" else status,
            "start_time": float(start) if start is not None else None,
            "end_time": float(end) if end is not None else None,
            "duration_ms": duration_ms,
            "attributes": {
                "execution_id": execution_id,
                "agent_id": rec.get("agent_id"),
                "skill_name": rec.get("skill_name"),
                "source": "synthesized_from_execution",
            },
        })
    except Exception:  # noqa: cleanup-best-effort
        pass
    trace = await store.get_trace(trace_id, include_spans=True)
    if not trace:
        trace = {
            "trace_id": trace_id,
            "name": f"{kind}:{name_key}",
            "status": status,
            "start_time": start,
            "end_time": end,
            "duration_ms": duration_ms,
            "attributes": {"execution_id": execution_id, "source": "synthesized_from_execution"},
            "spans": [],
        }
    spans = await _merged_diag_spans(store, execution_id, trace_id, existing=trace.get("spans") or [])
    trace["spans"] = spans
    return trace


@router.get("/executions/{execution_id}/trace", response_model=Dict[str, Any])
async def get_trace_by_execution(execution_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get trace (with spans) by execution_id (agent/skill)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    trace_id = await store.get_trace_id_by_execution_id(execution_id)
    if not trace_id:
        # Last resort: invent stable id from execution so heal path can still run
        rec = await _load_execution_record(store, execution_id)
        if not rec:
            raise HTTPException(status_code=404, detail=f"Trace not found for execution {execution_id}")
        trace_id = rec.get("trace_id") or f"trace-synth-{execution_id}"
    trace = await store.get_trace(trace_id, include_spans=True)
    if not trace:
        trace = await _heal_or_synthesize_trace(store, execution_id, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    # Workspace agents rarely write TraceService spans; merge syscall + run_graph.
    merged = await _merged_diag_spans(
        store, execution_id, str(trace_id), existing=trace.get("spans") or []
    )
    if merged:
        trace["spans"] = merged
    trace["start_time"] = _iso(trace.get("start_time"))
    trace["end_time"] = _iso(trace.get("end_time"))
    return trace


@router.get("/executions/{execution_id}/status", response_model=Dict[str, Any])
async def get_execution_status(execution_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get agent/skill/run_graph execution status (for frontend polling).

    Lookup order: agent_executions → skill_executions → run_graph_meta → run_events.
    Missing records return 200 + ``not_found`` (not 404) so live pollers do not spam
    console errors for short-lived or graph-only runs.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    eid = str(execution_id or "").strip()
    record = await store.get_agent_execution(eid) if eid else None
    kind = "agent"
    if not record:
        try:
            record = await store.get_skill_execution(eid)
            kind = "skill"
        except Exception:
            record = None
    if record:
        st = str(record.get("status") or "unknown").lower()
        # Orphan recovery: stream background died / hung past wall clock — status poll
        # must not spin forever on running with empty progress.
        if st in ("running", "accepted", "started", "pending"):
            try:
                import asyncio as _aio
                import time as _time
                import os as _os

                try:
                    probe_budget = float(
                        _os.getenv("AIPLAT_STATUS_ORPHAN_PROBE_SECONDS", "8") or "8"
                    )
                except Exception:
                    probe_budget = 8.0

                async def _orphan_probe() -> Optional[Dict[str, Any]]:
                    start = float(record.get("start_time") or 0.0)
                    age = (_time.time() - start) if start > 0 else 0.0
                    meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
                    mt = 0.0
                    try:
                        mt = float(meta.get("timeout") or 0)
                    except Exception:
                        mt = 0.0
                    # After skill-internal wait_for should have fired (+45s slack).
                    # Do NOT raise the wall with max(540, mt*1.15) — that made 480s skills
                    # appear stuck for ~9 minutes before UI stopped spinning.
                    # Agents without metadata.timeout get a longer default than skills
                    # (ReAct + nested skill LLM); prefer seeded metadata.timeout when set.
                    if kind == "agent":
                        default_wall = float(
                            _os.getenv("AIPLAT_AGENT_STREAM_ORPHAN_SECONDS", "900") or "900"
                        )
                    else:
                        default_wall = float(_os.getenv("AIPLAT_STREAM_ORPHAN_SECONDS", "360") or "360")
                    wall = (mt + 45.0) if mt > 0 else default_wall
                    # Stall must sit above in-flight sys_llm_generate wait_for.
                    # Local models often burn nearly the full LLM timeout; killing at
                    # 240s while generate is still healthy caused architect false timeouts.
                    from core.harness.utils.execute_session import (
                        llm_generate_event_stall_limit,
                        llm_generate_stall_seconds,
                        post_llm_zombie_grace_seconds,
                        skill_call_in_flight_after,
                        has_progress_after_generate,
                    )

                    stall_sec = float(llm_generate_stall_seconds())

                    llm_stalled = False
                    no_progress = False
                    post_llm_zombie = False
                    stall_reason = "llm_generate_stalled"

                    # Recover completed delivery BEFORE stall/graph probes.
                    # Those probes can eat the 8s status budget so auto_done
                    # never reaches finalize (qa_agent run-124d89d5ef3f).
                    if age >= 12.0 and kind == "agent" and hasattr(store, "list_syscall_events"):
                        try:
                            from core.harness.utils.execute_session import (
                                finalize_agent_after_skill_delivery,
                                orphan_skill_delivery_answer,
                            )

                            ev_early = await store.list_syscall_events(run_id=eid, limit=80)
                            items_early = (
                                (ev_early or {}).get("items")
                                if isinstance(ev_early, dict)
                                else (ev_early or [])
                            )
                            delivery_early = orphan_skill_delivery_answer(items_early or [])
                            if len(delivery_early) >= 40:
                                ok_early = await _aio.wait_for(
                                    finalize_agent_after_skill_delivery(
                                        run_id=eid,
                                        agent_id=str(record.get("agent_id") or "unknown"),
                                        output_text=delivery_early,
                                        start_time=start or None,
                                        trace_id=str(record.get("trace_id") or ""),
                                        metadata_extra={
                                            "orphan_watchdog": True,
                                            "orphan_reason": "finalize_after_skill_delivery",
                                            "finalize_source": "status_orphan_watch",
                                        },
                                    ),
                                    timeout=5.0,
                                )
                                if ok_early:
                                    return {
                                        "execution_id": eid,
                                        "kind": kind,
                                        "status": "completed",
                                        "end_time": _time.time(),
                                        "duration_ms": int(age * 1000),
                                        "output": {"text": delivery_early},
                                        "input": record.get("input"),
                                        "error": None,
                                        "quality_review": (
                                            (record.get("metadata") or {}).get("quality_review")
                                            if isinstance(record.get("metadata"), dict)
                                            else None
                                        ),
                                        "not_found": False,
                                        "recovered_skill_delivery": True,
                                    }
                        except Exception:
                            logging.debug(
                                "early skill_delivery orphan finalize failed for %s",
                                eid,
                                exc_info=True,
                            )

                    try:
                        # Background died before first LLM (UI stuck on ▶ Agent with 0 steps).
                        try:
                            no_prog_after = float(
                                _os.getenv("AIPLAT_AGENT_NO_PROGRESS_SECONDS", "90") or "90"
                            )
                        except Exception:
                            no_prog_after = 90.0
                        if (
                            kind == "agent"
                            and age >= max(30.0, no_prog_after)
                            and hasattr(store, "list_syscall_events")
                        ):
                            ev0 = await store.list_syscall_events(run_id=eid, limit=50)
                            items0 = (ev0 or {}).get("items") if isinstance(ev0, dict) else (ev0 or [])
                            progress_hits = 0
                            for it in items0 or []:
                                if not isinstance(it, dict):
                                    continue
                                kind_i = str(it.get("kind") or "").lower()
                                name_i = str(it.get("name") or "").lower()
                                if kind_i in ("llm", "skill", "tool", "routing", "mcp") or name_i in (
                                    "generate",
                                    "skill_route",
                                    "observation",
                                    "auto_done",
                                    "final_answer",
                                ):
                                    progress_hits += 1
                            if progress_hits == 0:
                                no_progress = True

                        if age >= min(stall_sec, 45.0) and hasattr(store, "list_syscall_events"):
                            ev = await store.list_syscall_events(run_id=eid, limit=50)
                            items = (ev or {}).get("items") if isinstance(ev, dict) else (ev or [])
                            now_ts = _time.time()
                            # Only the newest in-flight generate — stale unclosed rows from an
                            # earlier step must not orphan a healthy later call.
                            newest = None
                            newest_s0 = -1.0
                            for it in items or []:
                                if not isinstance(it, dict):
                                    continue
                                if str(it.get("kind") or "") != "llm":
                                    continue
                                if str(it.get("name") or "") != "generate":
                                    continue
                                if str(it.get("status") or "").lower() != "running":
                                    continue
                                s0 = float(it.get("start_time") or 0.0)
                                if s0 <= 0:
                                    continue
                                if s0 >= newest_s0:
                                    newest_s0 = s0
                                    newest = it
                            if newest is not None:
                                limit = llm_generate_event_stall_limit(newest, fallback=stall_sec)
                                if (now_ts - newest_s0) >= limit:
                                    # If a skill/tool container is still running, the nested
                                    # generate may be a live local to_thread zombie past
                                    # wait_for — do not orphan the Agent until the parent
                                    # skill/tool itself exceeds the same stall budget
                                    # (run-870f: skill architecture_design still active).
                                    parent_alive = False
                                    for it in items or []:
                                        if not isinstance(it, dict):
                                            continue
                                        kind_i = str(it.get("kind") or "").lower()
                                        st_i = str(it.get("status") or "").lower()
                                        if kind_i not in ("skill", "tool", "mcp"):
                                            continue
                                        if st_i != "running":
                                            continue
                                        s_parent = float(it.get("start_time") or 0.0)
                                        if s_parent <= 0:
                                            continue
                                        if (now_ts - s_parent) < limit:
                                            parent_alive = True
                                            break
                                    # skill_route selected but kind=skill not written yet
                                    if not parent_alive and skill_call_in_flight_after(
                                        items or [], after_ts=newest_s0 - 1.0
                                    ):
                                        parent_alive = True
                                    if not parent_alive:
                                        llm_stalled = True
                                        stall_sec = limit  # reflect in error message
                            # Zombie after generate already terminal (worker died /
                            # hung post-LLM). Stall probe above only sees running
                            # rows — blind when syscall is success but Agent/graph
                            # stay running (run-ff1319e103fd, canvas stuck on 推理).
                            if newest is None and kind == "agent" and not llm_stalled:
                                newest_done = None
                                newest_end = -1.0
                                for it in items or []:
                                    if not isinstance(it, dict):
                                        continue
                                    if str(it.get("kind") or "") != "llm":
                                        continue
                                    if str(it.get("name") or "") != "generate":
                                        continue
                                    st_i = str(it.get("status") or "").lower()
                                    if st_i not in (
                                        "success",
                                        "ok",
                                        "completed",
                                        "done",
                                        "timeout",
                                        "failed",
                                        "error",
                                    ):
                                        continue
                                    end_i = float(it.get("end_time") or 0.0)
                                    if end_i <= 0:
                                        try:
                                            end_i = float(it.get("start_time") or 0.0) + (
                                                float(it.get("duration_ms") or 0.0) / 1000.0
                                            )
                                        except Exception:
                                            end_i = 0.0
                                    if end_i >= newest_end:
                                        newest_end = end_i
                                        newest_done = it
                                if newest_done is not None and newest_end > 0:
                                    grace = float(post_llm_zombie_grace_seconds())
                                    if (now_ts - newest_end) >= grace:
                                        # Any newer progress after that generate?
                                        progressed = has_progress_after_generate(
                                            items or [], newest_end
                                        )
                                        # In-flight skill: route selected, skill row not
                                        # terminal yet (run-c32ebc4df1eb false zombie).
                                        if not progressed and skill_call_in_flight_after(
                                            items or [], after_ts=newest_end
                                        ):
                                            progressed = True
                                        if not progressed:
                                            post_llm_zombie = True
                                            stall_reason = "post_llm_zombie"
                                            stall_sec = grace
                                            # Seal canvas 「推理 · generate」left running
                                            # after syscall already flipped to success.
                                            try:
                                                if hasattr(store, "list_run_graph_nodes") and hasattr(
                                                    store, "upsert_run_graph_node"
                                                ):
                                                    for node in await store.list_run_graph_nodes(eid):
                                                        if str(node.get("status") or "").lower() != "running":
                                                            continue
                                                        if str(node.get("name") or "") != "generate":
                                                            continue
                                                        await store.upsert_run_graph_node(
                                                            {
                                                                "run_id": eid,
                                                                "node_id": node.get("node_id"),
                                                                "parent_id": node.get("parent_id"),
                                                                "kind": node.get("kind") or "llm",
                                                                "name": "generate",
                                                                "label": node.get("label") or "generate",
                                                                "role": node.get("role") or "work",
                                                                "status": "ok"
                                                                if str(newest_done.get("status") or "").lower()
                                                                in ("success", "ok", "completed", "done")
                                                                else "error",
                                                                "start_time": node.get("start_time") or newest_end,
                                                                "end_time": newest_end,
                                                                "duration_ms": newest_done.get("duration_ms")
                                                                or node.get("duration_ms"),
                                                                "args": node.get("args") or {},
                                                                "updated_at": now_ts,
                                                            }
                                                        )
                                            except Exception:
                                                logging.debug(
                                                    "post_llm_zombie graph seal failed for %s",
                                                    eid,
                                                    exc_info=True,
                                                )
                            # Stuck in 「准备 · LLM 前置」with zero llm:* — prep hang,
                            # not a slow Ollama generate. Orphan much earlier than 540s.
                            # Skip when any llm generate OR skill already started/finished:
                            # pre_llm_prep may stay ``running`` if close-before-generate
                            # raced (run-c8dda3ff18d4) OR skill-first paths never emit
                            # llm:generate rows (run-2ff29a641bf5: code_generation ok
                            # then false pre_llm_prep_stalled killed autoreview mid-flight).
                            # Also skip when skill_route selected but kind=skill not yet
                            # written (sys_skill_call defers skill row until completion —
                            # run-320e4de31f66: false prep stall at 60s mid code_generation).
                            if newest is None and kind == "agent":
                                has_exec_progress = False
                                for it in items or []:
                                    if not isinstance(it, dict):
                                        continue
                                    kind_i = str(it.get("kind") or "").lower()
                                    name_i = str(it.get("name") or "").lower()
                                    st_i = str(it.get("status") or "").lower()
                                    if st_i not in (
                                        "running",
                                        "success",
                                        "ok",
                                        "completed",
                                        "timeout",
                                        "failed",
                                        "error",
                                        "decision",
                                        "eval",
                                        "selected",
                                    ):
                                        continue
                                    if kind_i == "llm" and name_i == "generate":
                                        has_exec_progress = True
                                        break
                                    if kind_i == "skill":
                                        has_exec_progress = True
                                        break
                                    if kind_i == "routing" and name_i == "skill_route":
                                        has_exec_progress = True
                                        break
                                if not has_exec_progress and skill_call_in_flight_after(
                                    items or [], after_ts=0.1
                                ):
                                    has_exec_progress = True
                                if has_exec_progress:
                                    pass
                                else:
                                    try:
                                        prep_stall = float(
                                            _os.getenv("AIPLAT_PRE_LLM_STALL_SECONDS", "60") or "60"
                                        )
                                    except Exception:
                                        prep_stall = 60.0
                                    prep_stall = max(20.0, prep_stall)
                                    for it in items or []:
                                        if not isinstance(it, dict):
                                            continue
                                        if str(it.get("kind") or "").lower() != "context":
                                            continue
                                        if str(it.get("name") or "") != "pre_llm_prep":
                                            continue
                                        if str(it.get("status") or "").lower() != "running":
                                            continue
                                        s0 = float(it.get("start_time") or 0.0)
                                        if s0 > 0 and (now_ts - s0) >= prep_stall:
                                            llm_stalled = True
                                            stall_sec = prep_stall
                                            stall_reason = "pre_llm_prep_stalled"
                                            break
                    except Exception:
                        logging.debug("llm stall probe failed for %s", eid, exc_info=True)

                    # Loop declared done (skill_delivery_once or conversational auto_done)
                    # but Agent row still running (POST_LOOP hang). Recover as completed —
                    # do NOT timeout a good product. Coding Agents still require
                    # skill_delivery_once (not bare skill / premature auto_done) so
                    # autoreview is not skipped (run-073bd173ac06). Conversational
                    # Agents (qa_agent) only emit auto_done (run-124d89d5ef3f).
                    if age >= 12.0 and kind == "agent" and hasattr(store, "list_syscall_events"):
                        try:
                            from core.harness.utils.execute_session import (
                                finalize_agent_after_skill_delivery,
                                orphan_skill_delivery_answer,
                            )

                            ev_d = await store.list_syscall_events(run_id=eid, limit=80)
                            items_d = (ev_d or {}).get("items") if isinstance(ev_d, dict) else (ev_d or [])
                            delivery_answer = orphan_skill_delivery_answer(items_d or [])
                            if len(delivery_answer) >= 40:
                                ok = await finalize_agent_after_skill_delivery(
                                    run_id=eid,
                                    agent_id=str(record.get("agent_id") or "unknown"),
                                    output_text=delivery_answer,
                                    start_time=start or None,
                                    trace_id=str(record.get("trace_id") or ""),
                                    metadata_extra={
                                        "orphan_watchdog": True,
                                        "orphan_reason": "finalize_after_skill_delivery",
                                        "finalize_source": "status_orphan_watch",
                                    },
                                )
                                if ok:
                                    return {
                                        "execution_id": eid,
                                        "kind": kind,
                                        "status": "completed",
                                        "end_time": _time.time(),
                                        "duration_ms": int(age * 1000),
                                        "output": {"text": delivery_answer},
                                        "input": record.get("input"),
                                        "error": None,
                                        "quality_review": (
                                            (record.get("metadata") or {}).get("quality_review")
                                            if isinstance(record.get("metadata"), dict)
                                            else None
                                        ),
                                        "not_found": False,
                                        "recovered_skill_delivery": True,
                                    }
                        except Exception:
                            logging.debug(
                                "skill_delivery orphan finalize failed for %s", eid, exc_info=True
                            )

                    lock_expired_stale = False
                    try:
                        # Only runs that *held* a session_lock can be lock_expired_stale.
                        # Workspace agent stream executes never acquire a lock; treating
                        # "no lock" as stale falsely timeout'd them at age>=180s.
                        if age >= 180 and hasattr(store, "has_any_session_lock_for_run"):
                            had_lock = await store.has_any_session_lock_for_run(run_id=eid)
                            if had_lock and hasattr(store, "has_active_session_lock_for_run"):
                                alive = await store.has_active_session_lock_for_run(run_id=eid)
                                lock_expired_stale = not bool(alive)
                        elif age >= 180 and hasattr(store, "has_active_session_lock_for_run"):
                            # Legacy store without has_any: keep prior probe (skills only).
                            alive = await store.has_active_session_lock_for_run(run_id=eid)
                            lock_expired_stale = not bool(alive)
                        if age >= 180 and hasattr(store, "delete_expired_session_locks"):
                            await store.delete_expired_session_locks()
                    except Exception:
                        logging.debug("lock stale probe failed for %s", eid, exc_info=True)

                    should_orphan = (
                        age > max(60.0, wall)
                        or llm_stalled
                        or post_llm_zombie
                        or no_progress
                        or lock_expired_stale
                    )
                    if not should_orphan:
                        return None
                    reason = (
                        stall_reason
                        if (llm_stalled or post_llm_zombie)
                        else (
                            "no_progress"
                            if no_progress
                            else ("lock_expired_stale" if lock_expired_stale else "wall_exceeded")
                        )
                    )
                    err = (
                        f"orphan_watchdog({reason}): status stuck {st} for {int(age)}s "
                        f"(wall={int(wall)}s stall={int(stall_sec)}s); marked timeout"
                    )
                    end_t = _time.time()
                    patch = {
                        "id": eid,
                        "status": "timeout",
                        "error": err,
                        "end_time": end_t,
                        "duration_ms": int(age * 1000),
                        "input": record.get("input"),
                        "output": record.get("output"),
                        "skill_id": record.get("skill_id") or record.get("agent_id") or "unknown",
                        "agent_id": record.get("agent_id") or record.get("skill_id") or "unknown",
                        "start_time": start or end_t,
                        "user_id": record.get("user_id"),
                        "metadata": {**(meta or {}), "orphan_watchdog": True, "orphan_reason": reason},
                    }
                    # Persist timeout FIRST so pollers stop spinning even if cleanup hangs.
                    try:
                        if kind == "skill" and hasattr(store, "upsert_skill_execution"):
                            await store.upsert_skill_execution(patch)
                        elif kind == "agent" and hasattr(store, "upsert_agent_execution"):
                            await store.upsert_agent_execution(patch)
                    except Exception:
                        logging.warning("orphan upsert timeout status failed for %s", eid, exc_info=True)

                    async def _orphan_cleanup() -> None:
                        try:
                            if hasattr(store, "release_session_locks_for_run"):
                                await store.release_session_locks_for_run(run_id=eid)
                            if hasattr(store, "delete_expired_session_locks"):
                                await store.delete_expired_session_locks()
                        except Exception:
                            logging.debug("orphan lock cleanup failed for %s", eid, exc_info=True)
                        # Never block status HTTP on Ollama unload (can wedge all gunicorn threads).
                        try:
                            from core.harness.utils.local_llm_recover import unload_local_llm_best_effort

                            await _aio.wait_for(
                                _aio.to_thread(unload_local_llm_best_effort),
                                timeout=3.0,
                            )
                        except Exception:
                            logging.debug("orphan ollama unload skipped/failed for %s", eid, exc_info=True)
                        try:
                            if hasattr(store, "close_running_syscall_events"):
                                await store.close_running_syscall_events(
                                    eid,
                                    status="timeout",
                                    error=err,
                                    error_code="ORPHAN_WATCHDOG",
                                )
                        except Exception:
                            logging.debug("orphan llm event close failed for %s", eid, exc_info=True)
                        try:
                            if hasattr(store, "set_run_graph_status"):
                                await store.set_run_graph_status(eid, "timeout")
                            if hasattr(store, "list_run_graph_nodes"):
                                nodes = await store.list_run_graph_nodes(eid)
                                for n in nodes or []:
                                    if str((n or {}).get("status") or "").lower() != "running":
                                        continue
                                    nid = (n or {}).get("node_id")
                                    if not nid:
                                        continue
                                    try:
                                        from core.harness.observation.run_graph import close_node

                                        await close_node(
                                            eid,
                                            str(nid),
                                            status="error",
                                            error=err,
                                            audit=False,
                                        )
                                    except Exception:
                                        logging.debug("orphan close_node failed", exc_info=True)
                        except Exception:
                            logging.debug("orphan graph close failed for %s", eid, exc_info=True)
                        try:
                            await store.append_run_event(
                                run_id=eid,
                                event_type="run_end",
                                trace_id=None,
                                tenant_id=None,
                                payload={"status": "timeout", "reason": reason, "error": err},
                            )
                        except Exception:
                            logging.debug("orphan run_end failed for %s", eid, exc_info=True)

                    try:
                        _aio.create_task(_orphan_cleanup())
                    except Exception:
                        # Fallback: best-effort inline without unload
                        try:
                            if hasattr(store, "close_running_syscall_events"):
                                await store.close_running_syscall_events(
                                    eid, status="timeout", error=err, error_code="ORPHAN_WATCHDOG"
                                )
                            if hasattr(store, "set_run_graph_status"):
                                await store.set_run_graph_status(eid, "timeout")
                        except Exception:
                            logging.debug("orphan inline cleanup failed for %s", eid, exc_info=True)
                    return {
                        "execution_id": eid,
                        "kind": kind,
                        "status": "timeout",
                        "end_time": end_t,
                        "duration_ms": int(age * 1000),
                        "output": record.get("output"),
                        "input": record.get("input"),
                        "error": err,
                        "not_found": False,
                    }

                try:
                    override = await _aio.wait_for(
                        _orphan_probe(), timeout=max(2.0, float(probe_budget))
                    )
                    if isinstance(override, dict):
                        return override
                except _aio.TimeoutError:
                    logging.warning(
                        "status orphan probe timed out execution_id=%s budget=%.1fs",
                        eid,
                        probe_budget,
                    )
                    # Probe wedged (SQLite lock while LLM to_thread runs).
                    # Previously we only soft-killed at soft_wall≈900s and returned
                    # ``running`` forever under that wall — so when probe itself hung,
                    # llm_generate_stalled never ran and UI blocked 10+ min
                    # (run-9ce13fd009cb age≈659s, ollama empty, status API timed out).
                    # If age already exceeds the LLM stall floor, mark timeout even
                    # without a successful probe.
                    try:
                        import time as _time_soft

                        soft_age = (
                            (_time_soft.time() - float(record.get("start_time") or 0.0))
                            if float(record.get("start_time") or 0.0) > 0
                            else 0.0
                        )
                        from core.harness.utils.execute_session import (
                            llm_generate_stall_seconds as _stall_floor_fn,
                        )

                        stall_floor = float(_stall_floor_fn())
                        soft_wall = float(
                            _os.getenv("AIPLAT_AGENT_STREAM_ORPHAN_SECONDS", "900") or "900"
                        )
                        try:
                            _mt = float(
                                (record.get("metadata") or {}).get("timeout") or 0
                            ) if isinstance(record.get("metadata"), dict) else 0.0
                            if _mt > 0:
                                soft_wall = _mt + 45.0
                        except Exception:
                            pass  # noqa: cleanup-best-effort
                        try:
                            soft_ceil = float(
                                _os.getenv("AIPLAT_AGENT_STREAM_ORPHAN_MAX_SECONDS", "2400")
                                or "2400"
                            )
                            soft_wall = min(soft_wall, soft_ceil)
                        except Exception:
                            pass  # noqa: cleanup-best-effort

                        # Still within healthy generate budget → return running fast.
                        if soft_age < max(120.0, stall_floor):
                            logging.info(
                                "orphan probe_timeout ignored under stall floor: "
                                "execution_id=%s age=%ss stall=%ss",
                                eid,
                                int(soft_age),
                                int(stall_floor),
                            )
                            return {
                                "execution_id": eid,
                                "kind": kind,
                                "status": record.get("status") or "running",
                                "end_time": record.get("end_time"),
                                "duration_ms": record.get("duration_ms"),
                                "output": record.get("output"),
                                "input": record.get("input"),
                                "error": record.get("error"),
                                "not_found": False,
                                "probe_timeout": True,
                                "probe_timeout_deferred": True,
                            }

                        # Past stall floor (or absolute soft wall): mark timeout so UI
                        # unblocks even when syscall listing is wedged.
                        kill_age = soft_age
                        soft_err = (
                            f"orphan_watchdog(llm_generate_stalled): status probe "
                            f"exceeded {probe_budget:.0f}s while run age="
                            f"{int(kill_age)}s (stall={int(stall_floor)}s "
                            f"wall={int(soft_wall)}s); marked timeout"
                        )
                        soft_end = _time_soft.time()
                        soft_out = record.get("output")
                        soft_patch = {
                            "id": eid,
                            "status": "timeout",
                            "error": soft_err,
                            "end_time": soft_end,
                            "duration_ms": int(kill_age * 1000),
                            "input": record.get("input"),
                            "skill_id": record.get("skill_id")
                            or record.get("agent_id")
                            or "unknown",
                            "agent_id": record.get("agent_id")
                            or record.get("skill_id")
                            or "unknown",
                            "start_time": float(
                                record.get("start_time") or soft_end
                            ),
                            "user_id": record.get("user_id"),
                            "metadata": {
                                **(
                                    record.get("metadata")
                                    if isinstance(record.get("metadata"), dict)
                                    else {}
                                ),
                                "orphan_watchdog": True,
                                "orphan_reason": "llm_generate_stalled",
                                "orphan_via": "probe_timeout_past_stall",
                            },
                        }
                        if soft_out is not None:
                            soft_patch["output"] = soft_out

                        async def _soft_upsert_stall() -> None:
                            try:
                                if kind == "skill" and hasattr(
                                    store, "upsert_skill_execution"
                                ):
                                    await store.upsert_skill_execution(soft_patch)
                                elif hasattr(store, "upsert_agent_execution"):
                                    await store.upsert_agent_execution(soft_patch)
                                if hasattr(store, "close_running_syscall_events"):
                                    await store.close_running_syscall_events(
                                        eid,
                                        status="timeout",
                                        error=soft_err,
                                        error_code="ORPHAN_WATCHDOG",
                                    )
                            except Exception:
                                logging.debug(
                                    "soft stall upsert failed for %s",
                                    eid,
                                    exc_info=True,
                                )

                        try:
                            _aio.create_task(_soft_upsert_stall())
                        except Exception:
                            pass  # noqa: cleanup-best-effort
                        # Best-effort local LLM unload so next run is not queued
                        try:
                            from core.harness.utils.local_llm_recover import (
                                unload_local_llm_best_effort,
                            )

                            _aio.create_task(
                                _aio.to_thread(unload_local_llm_best_effort)
                            )
                        except Exception:
                            pass  # noqa: cleanup-best-effort
                        return {
                            "execution_id": eid,
                            "kind": kind,
                            "status": "timeout",
                            "end_time": soft_end,
                            "duration_ms": int(kill_age * 1000),
                            "output": soft_out,
                            "input": soft_patch.get("input"),
                            "error": soft_err,
                            "not_found": False,
                            "probe_timeout": True,
                        }
                    except Exception:
                        logging.debug(
                            "soft timeout after probe fail skipped for %s",
                            eid,
                            exc_info=True,
                        )
            except Exception:
                logging.debug("orphan_watchdog failed for %s", eid, exc_info=True)
        # Nested skill envelope: outer row may say completed/failed while payload carries detail
        status_out = str(record.get("status") or "unknown")
        err_out = record.get("error")
        out_val = record.get("output")
        try:
            if isinstance(out_val, dict):
                nested_st = str(out_val.get("status") or "").lower()
                nested_err = out_val.get("error") or out_val.get("error_message")
                if status_out.lower() in ("completed", "ok", "success", "done") and nested_st in (
                    "timeout",
                    "failed",
                    "error",
                    "cancelled",
                    "canceled",
                ):
                    status_out = "timeout" if nested_st == "timeout" else (
                        "cancelled" if nested_st in ("cancelled", "canceled") else "failed"
                    )
                if not err_out and nested_err:
                    if isinstance(nested_err, dict):
                        err_out = nested_err.get("message") or nested_err.get("code") or str(nested_err)
                    else:
                        err_out = nested_err
        except Exception:
            logging.debug("nested status unwrap failed for %s", eid, exc_info=True)
        _qr = None
        try:
            _meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            if isinstance(_meta.get("quality_review"), dict):
                _qr = _meta.get("quality_review")
        except Exception:
            _qr = None
        return {
            "execution_id": eid,
            "kind": kind,
            "status": status_out,
            "end_time": record.get("end_time"),
            "duration_ms": record.get("duration_ms"),
            "output": out_val,
            "input": record.get("input"),
            "error": err_out,
            "quality_review": _qr,
            "not_found": False,
        }

    # Authoritative RunGraph projection (Skill/Agent may finish graph before row upsert races)
    try:
        rg_status = await store.get_run_graph_status(eid) if eid and hasattr(store, "get_run_graph_status") else None
    except Exception:
        rg_status = None
    if rg_status:
        st = str(rg_status).lower()
        if st in ("completed", "ok", "success", "done"):
            mapped = "completed"
        elif st in ("failed", "error", "timeout"):
            mapped = "failed" if st != "timeout" else "timeout"
        else:
            mapped = st or "running"
        # Race: graph closes before agent/skill row upsert — re-read row; if still empty,
        # keep status as running so pollers wait for output instead of empty_output fail.
        out_val = None
        err_out = None
        in_val = None
        dur = None
        row_terminal = False
        try:
            record2 = None
            if hasattr(store, "get_agent_execution"):
                record2 = await store.get_agent_execution(eid)
            if not record2 and hasattr(store, "get_skill_execution"):
                record2 = await store.get_skill_execution(eid)
            if isinstance(record2, dict):
                out_val = record2.get("output")
                err_out = record2.get("error")
                in_val = record2.get("input")
                dur = record2.get("duration_ms")
                row_st = str(record2.get("status") or "").lower()
                if row_st in ("failed", "error", "timeout", "cancelled", "canceled"):
                    mapped = row_st if row_st != "error" else "failed"
                    row_terminal = True
                elif row_st in ("completed", "ok", "success", "done"):
                    mapped = "completed"
                    row_terminal = True
        except Exception:
            logging.debug("run_graph status row re-read failed for %s", eid, exc_info=True)
        # Only stall as pending_output when the execution ROW is not terminal yet.
        # A completed/timeout row with empty output must surface honestly (do not spin forever).
        if mapped == "completed" and not row_terminal:
            textish = ""
            if isinstance(out_val, str):
                textish = out_val.strip()
            elif isinstance(out_val, dict):
                textish = str(out_val.get("text") or out_val.get("output") or "").strip()
                if not textish and out_val:
                    textish = "1"  # non-empty structured payload counts
            if not textish and not err_out:
                return {
                    "execution_id": eid,
                    "kind": "run_graph",
                    "status": "running",
                    "end_time": None,
                    "duration_ms": dur,
                    "output": out_val,
                    "input": in_val,
                    "error": None,
                    "pending_output": True,
                    "not_found": False,
                }
        return {
            "execution_id": eid,
            "kind": "run_graph",
            "status": mapped,
            "end_time": None,
            "duration_ms": dur,
            "output": out_val,
            "input": in_val,
            "error": err_out,
            "not_found": False,
        }

    # Stream mode: harness appends run_start/run_end before skill_executions row exists.
    # Treat run_events as authoritative so pollers do not see status=unknown mid-flight.
    try:
        if eid and hasattr(store, "has_run_end") and await store.has_run_end(run_id=eid):
            end_status = "completed"
            end_error = None
            try:
                if hasattr(store, "list_run_events"):
                    ev = await store.list_run_events(run_id=eid, after_seq=0, limit=500)
                    items = (ev or {}).get("items") if isinstance(ev, dict) else []
                    for it in reversed(items or []):
                        if str((it or {}).get("type") or "") != "run_end":
                            continue
                        payload = (it or {}).get("payload") if isinstance((it or {}).get("payload"), dict) else {}
                        st = str(payload.get("status") or "").lower()
                        if st in ("failed", "error"):
                            end_status = "failed"
                            end_error = payload.get("error") or payload.get("message")
                        elif st == "timeout":
                            end_status = "timeout"
                            end_error = payload.get("error") or payload.get("message")
                        elif st in ("cancelled", "canceled"):
                            end_status = "cancelled"
                        elif st in ("completed", "ok", "success", "done", ""):
                            end_status = "completed"
                        break
            except Exception:
                logging.debug("run_end payload parse failed for %s", eid, exc_info=True)
            out_val = None
            row_terminal = False
            try:
                record2 = None
                if hasattr(store, "get_agent_execution"):
                    record2 = await store.get_agent_execution(eid)
                if not record2 and hasattr(store, "get_skill_execution"):
                    record2 = await store.get_skill_execution(eid)
                if isinstance(record2, dict):
                    out_val = record2.get("output")
                    if record2.get("error") and not end_error:
                        end_error = record2.get("error")
                    row_st = str(record2.get("status") or "").lower()
                    if row_st in ("failed", "error", "timeout", "cancelled", "canceled"):
                        end_status = row_st if row_st != "error" else "failed"
                        row_terminal = True
                    elif row_st in ("completed", "ok", "success", "done"):
                        end_status = "completed"
                        row_terminal = True
            except Exception:
                logging.debug("run_events status row re-read failed for %s", eid, exc_info=True)
            if end_status == "completed" and not end_error and not row_terminal:
                textish = ""
                if isinstance(out_val, str):
                    textish = out_val.strip()
                elif isinstance(out_val, dict) and out_val:
                    textish = str(out_val.get("text") or out_val.get("output") or "1").strip()
                if not textish:
                    return {
                        "execution_id": eid,
                        "kind": "run_events",
                        "status": "running",
                        "end_time": None,
                        "duration_ms": None,
                        "output": out_val,
                        "error": None,
                        "pending_output": True,
                        "not_found": False,
                    }
            return {
                "execution_id": eid,
                "kind": "run_events",
                "status": end_status,
                "end_time": None,
                "duration_ms": None,
                "output": out_val,
                "error": end_error,
                "not_found": False,
            }
    except Exception:
        logging.debug("has_run_end check failed for %s", eid, exc_info=True)

    try:
        if eid and hasattr(store, "get_run_start_event"):
            start_ev = await store.get_run_start_event(run_id=eid)
            if start_ev:
                payload = start_ev.get("payload") if isinstance(start_ev.get("payload"), dict) else {}
                start_status = str(payload.get("status") or "").lower()
                # Queued behind session lock — do not report as running (UI would spin
                # on empty steps forever while drain waits for a leaked lock).
                if start_status in ("queued", "pending"):
                    reason = None
                    q_session = None
                    try:
                        if hasattr(store, "list_run_events"):
                            ev = await store.list_run_events(run_id=eid, after_seq=0, limit=50)
                            items = (ev or {}).get("items") if isinstance(ev, dict) else []
                            for it in items or []:
                                if str((it or {}).get("type") or "") != "queued":
                                    continue
                                qp = (it or {}).get("payload") if isinstance((it or {}).get("payload"), dict) else {}
                                reason = qp.get("reason") or qp.get("session_id")
                                q_session = qp.get("session_id")
                                break
                    except Exception:
                        logging.debug("queued reason lookup failed for %s", eid, exc_info=True)
                    # Best-effort: expired/leaked locks leave the queue idle until something
                    # kicks drain — status polls are a natural wake-up signal.
                    try:
                        sid = str(q_session or payload.get("session_id") or "").strip()
                        if sid:
                            from core.harness.integration import get_harness

                            tid = start_ev.get("tenant_id") if isinstance(start_ev, dict) else None
                            get_harness()._kick_session_drain(
                                tenant_id=str(tid) if tid is not None else None,
                                session_id=sid,
                            )
                    except Exception:
                        logging.debug("queued status drain kick failed for %s", eid, exc_info=True)
                    return {
                        "execution_id": eid,
                        "kind": "run_events",
                        "status": "queued",
                        "end_time": None,
                        "duration_ms": None,
                        "output": None,
                        "error": f"session_locked:{reason}" if reason else "session_locked",
                        "queued": True,
                        "not_found": False,
                    }
                return {
                    "execution_id": eid,
                    "kind": "run_events",
                    "status": "running",
                    "end_time": None,
                    "duration_ms": None,
                    "output": None,
                    "error": None,
                    "not_found": False,
                }
    except Exception:
        logging.debug("get_run_start_event check failed for %s", eid, exc_info=True)

    return {
        "execution_id": eid,
        "kind": None,
        "status": "unknown",
        "end_time": None,
        "duration_ms": None,
        "output": None,
        "error": None,
        "not_found": True,
    }


@router.post("/executions/{execution_id}/cancel", response_model=Dict[str, Any])
async def cancel_execution(
    execution_id: str,
    body: Optional[Dict[str, Any]] = None,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    """User/UI stop for agent or skill executions stuck in running.

    Marks the row cancelled immediately, then best-effort closes syscall/graph
    and unloads local Ollama (non-blocking). Idempotent for already-terminal rows.
    """
    import asyncio as _aio
    import time as _time

    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    eid = str(execution_id or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="execution_id_required")

    kind = "agent"
    record = None
    try:
        record = await store.get_agent_execution(eid) if hasattr(store, "get_agent_execution") else None
    except Exception:
        record = None
    if not record:
        try:
            record = await store.get_skill_execution(eid) if hasattr(store, "get_skill_execution") else None
            kind = "skill"
        except Exception:
            record = None
    if not record:
        raise HTTPException(status_code=404, detail="execution_not_found")

    st = str(record.get("status") or "").lower()
    reason = "user_requested"
    if isinstance(body, dict) and body.get("reason"):
        reason = str(body.get("reason"))
    if st in ("completed", "ok", "success", "done", "timeout", "cancelled", "canceled", "failed", "error"):
        return {
            "status": st if st not in ("ok", "success", "done") else "completed",
            "execution_id": eid,
            "kind": kind,
            "already_terminal": True,
        }

    now = _time.time()
    start = float(record.get("start_time") or now)
    meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    err = f"cancelled({reason})"
    patch = {
        "id": eid,
        "status": "cancelled",
        "error": err,
        "end_time": now,
        "duration_ms": max(0, int((now - start) * 1000)),
        "input": record.get("input"),
        "output": record.get("output"),
        "skill_id": record.get("skill_id") or record.get("agent_id") or "unknown",
        "agent_id": record.get("agent_id") or record.get("skill_id") or "unknown",
        "start_time": start,
        "user_id": record.get("user_id"),
        "trace_id": record.get("trace_id"),
        "metadata": {**meta, "user_cancel": True, "cancel_reason": reason},
    }
    try:
        async def _persist() -> None:
            if kind == "skill" and hasattr(store, "upsert_skill_execution"):
                await store.upsert_skill_execution(patch)
            elif hasattr(store, "upsert_agent_execution"):
                await store.upsert_agent_execution(patch)

        await _aio.wait_for(_persist(), timeout=5.0)
    except _aio.TimeoutError:
        logging.warning("cancel upsert timed out for %s (store likely wedged)", eid)
    except Exception:
        logging.warning("cancel upsert failed for %s", eid, exc_info=True)
        raise HTTPException(status_code=500, detail="cancel_persist_failed")

    async def _cleanup() -> None:
        try:
            if hasattr(store, "close_running_syscall_events"):
                await store.close_running_syscall_events(
                    eid, status="cancelled", error=err, error_code="USER_CANCEL"
                )
        except Exception:
            logging.debug("cancel close syscalls failed for %s", eid, exc_info=True)
        try:
            if hasattr(store, "set_run_graph_status"):
                await store.set_run_graph_status(eid, "cancelled")
        except Exception:
            logging.debug("cancel graph status failed for %s", eid, exc_info=True)
        try:
            if hasattr(store, "append_run_event"):
                await store.append_run_event(
                    run_id=eid,
                    event_type="run_end",
                    trace_id=record.get("trace_id"),
                    tenant_id=None,
                    payload={"status": "cancelled", "reason": reason},
                )
        except Exception:
            logging.debug("cancel run_end failed for %s", eid, exc_info=True)
        try:
            from core.harness.utils.local_llm_recover import unload_local_llm_best_effort

            await _aio.wait_for(_aio.to_thread(unload_local_llm_best_effort), timeout=3.0)
        except Exception:
            logging.debug("cancel ollama unload skipped for %s", eid, exc_info=True)

    try:
        _aio.create_task(_cleanup())
    except Exception:
        logging.debug("cancel cleanup schedule failed for %s", eid, exc_info=True)

    return {
        "status": "cancelled",
        "execution_id": eid,
        "kind": kind,
        "already_terminal": False,
    }
