"""Mint per-execute session ids and agent stream wall budgets.

``session_id=default`` is a shared lock key in the session lane. A leaked stream
lock on that key queues every subsequent Skill/Agent/Tool/Graph execute with an
empty RunGraph until TTL/drain. Management trial executes must mint a unique id
when the caller did not supply a real conversation session.
"""
from __future__ import annotations

import ast
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional


def pre_llm_prep_close_ids(
    run_id: str,
    *,
    step_count: Any = None,
    parent_span_id: str = "",
) -> List[str]:
    """Syscall ids that must be closed together for 「准备 · LLM 前置」.

    Open uses ``{run}:pre_llm_prep:{step}``; several close paths historically
    wrote only ``{run}:pre_llm_prep``. UPSERT then never hits the running row
    (qa_agent run-124d89d5ef3f: auto_done ok, canvas stuck on step_2).
    """
    rid = str(run_id or "").strip()
    if not rid:
        return []
    ids: List[str] = [f"{rid}:pre_llm_prep"]
    steps: set[int] = set()
    try:
        n = int(step_count or 0)
        if n > 0:
            steps.add(n)
    except (TypeError, ValueError):
        pass  # noqa: cleanup-best-effort
    ps = str(parent_span_id or "").strip()
    if ps.startswith("step:"):
        try:
            steps.add(int(ps.rsplit(":", 1)[-1]))
        except (TypeError, ValueError):
            pass  # noqa: cleanup-best-effort
    # Previous-step leftover (step_1 still running when step_2 auto_done).
    steps |= {n - 1 for n in list(steps) if n > 1}
    for n in sorted(steps):
        ids.append(f"{rid}:pre_llm_prep:{n}")
    return ids


async def emit_pre_llm_prep_close(
    store: Any,
    run_id: str,
    *,
    status: str = "ok",
    step_count: Any = None,
    parent_span_id: str = "",
    reason: str = "",
    extra_args: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Close both legacy and stepped pre_llm_prep syscall rows."""
    import time as _t

    adder = getattr(store, "add_syscall_event", None)
    if not callable(adder):
        return
    rid = str(run_id or "").strip()
    if not rid:
        return
    now = _t.time()
    args: Dict[str, Any] = {"closed": reason or "pre_llm_prep_close"}
    if extra_args:
        args.update(extra_args)
    payload_base = {
        "span_id": f"{rid}:pre_llm_prep",
        "parent_span_id": parent_span_id or None,
        "kind": "context",
        "name": "pre_llm_prep",
        "status": status,
        "run_id": rid,
        "start_time": now,
        "end_time": now,
        "duration_ms": 0,
        "args": args,
    }
    if error:
        payload_base["error"] = error
    for eid in pre_llm_prep_close_ids(
        rid, step_count=step_count, parent_span_id=parent_span_id
    ):
        ev = dict(payload_base)
        ev["id"] = eid
        ev["span_id"] = eid
        maybe = adder(ev)
        if hasattr(maybe, "__await__"):
            await maybe
    closer = getattr(store, "close_running_syscall_events", None)
    if callable(closer):
        maybe_c = closer(
            rid,
            status=status,
            error=error,
            kind="context",
            name="pre_llm_prep",
        )
        if hasattr(maybe_c, "__await__"):
            await maybe_c


def coerce_coding_delivery_text(output_text: str) -> str:
    """Unwrap ``{code, language}`` JSON / Python-repr into the coding body.

    Skill observe often leaves ``str({'code': '...## FILE...', 'language': 'typescript'})``
    as the Agent delivery string. Sealing that as ``{"text": "<repr>"}`` forces the UI
    to show a dict dump (run-c896745b). Prefer the inner ``code`` when present.
    """
    s = str(output_text or "").strip()
    if not s or not s.startswith(("{", "[")):
        return s
    obj: Any = None
    try:
        obj = json.loads(s)
    except Exception:
        try:
            obj = ast.literal_eval(s)
        except Exception:
            return s
    if not isinstance(obj, dict):
        return s
    for k in ("code", "generated_code", "source", "snippet", "text", "markdown"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            # Nested repr one more level
            inner = v.strip()
            if inner.startswith("{") and ("'code'" in inner or '"code"' in inner):
                return coerce_coding_delivery_text(inner)
            if "## FILE:" in v or len(v.strip()) >= 40:
                return v
    return s


def skill_nested_llm_trace_context(
    context: Any = None,
    params: Optional[Dict[str, Any]] = None,
    *,
    source: str = "skill",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build ``sys_llm_generate`` trace_context for nested Skill LLM calls.

    Any Agent that calls any Skill (prompt / hybrid / handler) can hang the
    orphan watchdog if the nested generate has no ``run_id``. Do not limit this
    to ``code_generation``.
    """
    tc: Dict[str, Any] = {"source": str(source or "skill")}
    if extra:
        tc.update(extra)
    pdata = params if isinstance(params, dict) else {}
    vars_: Dict[str, Any] = {}
    try:
        raw = getattr(context, "variables", None) or {}
        if isinstance(raw, dict):
            vars_ = raw
    except Exception:
        vars_ = {}
    rid = str(
        vars_.get("_run_id")
        or pdata.get("_run_id")
        or getattr(context, "session_id", "")
        or ""
    ).strip()
    if rid.startswith(("run_", "run-")):
        tc["run_id"] = rid
        try:
            if isinstance(getattr(context, "variables", None), dict):
                context.variables.setdefault("_run_id", rid)
        except Exception:
            pass  # noqa: cleanup-best-effort
    psp = str(
        vars_.get("_parent_span_id")
        or vars_.get("parent_span_id")
        or pdata.get("_parent_span_id")
        or pdata.get("parent_span_id")
        or ""
    ).strip()
    if psp and re.match(r"^run[-_].+:skill:.+$", psp):
        psp = ""
    if not psp:
        try:
            from core.harness.kernel.execution_context import get_active_trace_context

            atc = get_active_trace_context()
            if atc is not None:
                psp = str(
                    getattr(atc, "span_id", "") or getattr(atc, "parent_span_id", "") or ""
                ).strip()
        except Exception:
            psp = ""
    if psp:
        tc["parent_span_id"] = psp
    elif rid:
        src = str(source or "skill").strip() or "skill"
        tc["parent_span_id"] = f"skill:{src}"
    return tc


def mint_execute_session_id(
    *,
    kind: str,
    target_id: str,
    session_id: Optional[str] = None,
) -> str:
    """Return a usable session id; replace empty / ``default`` with a unique trial id."""
    sid = str(session_id or "").strip()
    if sid and sid.lower() != "default":
        return sid
    safe_kind = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(kind or "exec").strip())[:24] or "exec"
    safe_target = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(target_id or "x").strip())[:48] or "x"
    return f"{safe_kind}-exec-{safe_target}-{uuid.uuid4().hex[:12]}"


def llm_timeout_seconds() -> float:
    """Single ``sys_llm_generate`` wait_for budget (env-driven)."""
    try:
        return float(
            os.getenv("AIPLAT_LLM_TIMEOUT_SECONDS")
            or os.getenv("AIPLAT_LLM_DEFAULT_TIMEOUT_SECONDS")
            or "180"
        )
    except Exception:
        return 180.0


def llm_generate_stall_seconds() -> float:
    """Global orphan probe floor for ``llm_generate_stalled``.

    Must sit **above** a healthy in-flight ``sys_llm_generate`` wait_for.
    TimeoutError is hard-excluded from ResilienceGate retries (OSError trap),
    so budget is one attempt + slack — not N×timeout.

    Local Ollama ``to_thread`` calls often outlive wait_for (zombie HTTP):
    run-b6f2 ~337s and run-870f ~359s with declare=180. Floor/slack must
    cover that overrun or status orphan kills a live skill mid-generate.

    Override with ``AIPLAT_STREAM_STALL_SECONDS`` (>0).
    """
    try:
        override = float(os.getenv("AIPLAT_STREAM_STALL_SECONDS", "0") or "0")
    except Exception:
        override = 0.0
    if override > 0:
        return override
    llm_to = max(30.0, llm_timeout_seconds())
    # Only non-timeout transport errors retry; do not multiply the stall floor
    # by AIPLAT_LLM_RETRIES (that caused 540–720s false 「执行中」).
    # Slack +180 (was +90): covers local zombie overrun past wait_for.
    return max(360.0, llm_to + 180.0)


def post_llm_zombie_grace_seconds() -> float:
    """How long after a terminal ``llm/generate`` the Agent may stay ``running``.

    Worker death / event-loop wedge after a successful generate leaves:
    - syscall generate already ``success``
    - run_graph generate card still ``running``
    - agent_executions still ``running``

    Orphan probes that only watch ``status=running`` generate rows are blind
    (run-ff1319e103fd). After this grace, status poll must timeout the Agent.
    """
    try:
        return max(30.0, float(os.getenv("AIPLAT_POST_LLM_ZOMBIE_SECONDS", "90") or "90"))
    except Exception:
        return 90.0


_SKILL_TERMINAL = frozenset(
    {
        "success",
        "ok",
        "completed",
        "done",
        "failed",
        "error",
        "timeout",
        "policy_denied",
        "approval_required",
    }
)


def skill_call_in_flight_after(items: Any, *, after_ts: float) -> bool:
    """True when a skill was routed after ``after_ts`` and has not terminalized yet.

    ``sys_skill_call`` emits ``routing/skill_route`` (selected) at start, but the
    ``kind=skill`` syscall row only appears on completion. Orphan ``post_llm_zombie``
    must treat that gap as live work — otherwise nested skill LLM is killed as a
    false zombie (run-c32ebc4df1eb: code_generation started, Agent timed out at 90s).
    """
    try:
        after = float(after_ts or 0.0)
    except Exception:
        after = 0.0
    if after <= 0:
        return False
    rows = items if isinstance(items, list) else []
    latest_route = -1.0
    for it in rows:
        if not isinstance(it, dict):
            continue
        if str(it.get("kind") or "").lower() != "routing":
            continue
        if str(it.get("name") or "").lower() != "skill_route":
            continue
        st = str(it.get("status") or "").lower()
        if st and st not in ("selected", "ok", "success", "running"):
            continue
        try:
            t = float(it.get("end_time") or it.get("start_time") or 0.0)
        except Exception:
            t = 0.0
        # skill_route often lands <500ms after generate (run-c32: ~180ms) —
        # do not require the +0.5s slack used for unrelated progress probes.
        if t >= after - 0.05:
            latest_route = max(latest_route, t)
    if latest_route < 0:
        # Also honor an open skill row if one was written mid-flight.
        for it in rows:
            if not isinstance(it, dict):
                continue
            if str(it.get("kind") or "").lower() != "skill":
                continue
            if str(it.get("status") or "").lower() != "running":
                continue
            try:
                t = float(it.get("start_time") or 0.0)
            except Exception:
                t = 0.0
            if t >= after - 0.05:
                return True
        return False
    for it in rows:
        if not isinstance(it, dict):
            continue
        if str(it.get("kind") or "").lower() != "skill":
            continue
        st = str(it.get("status") or "").lower()
        if st not in _SKILL_TERMINAL:
            continue
        try:
            t = float(it.get("end_time") or it.get("start_time") or 0.0)
        except Exception:
            t = 0.0
        if t >= latest_route - 0.05:
            return False
    return True


def has_progress_after_generate(items: Any, newest_end: float) -> bool:
    """True when skill/observe/done landed around the latest generate (not a zombie).

    Nested skill LLM and observation often finish <100ms after generate
    (architect run-e51daea7e4e4: observation start = generate_end + 73ms).
    Requiring ``t1 > newest_end + 0.5`` false-triggered ``post_llm_zombie``
    and timed out completed skills.
    """
    try:
        end = float(newest_end or 0.0)
    except Exception:
        end = 0.0
    if end <= 0:
        return False
    for it in items or []:
        if not isinstance(it, dict):
            continue
        kind_i = str(it.get("kind") or "").lower()
        name_i = str(it.get("name") or "").lower()
        if kind_i in ("skill", "tool", "mcp", "done", "observe") or name_i in (
            "skill_delivery_once",
            "auto_done",
            "final_answer",
            "observation",
        ):
            t1 = 0.0
            for key in ("end_time", "start_time", "created_at"):
                try:
                    v = float(it.get(key) or 0.0)
                except Exception:
                    v = 0.0
                if v > t1:
                    t1 = v
            if t1 >= end - 0.05:
                return True
    return False


def llm_generate_event_stall_limit(event: Optional[Dict[str, Any]], *, fallback: float) -> float:
    """Per-running-generate stall limit from syscall event args.timeout_seconds.

    Declared ``timeout_seconds`` is the ``sys_llm_generate`` wait_for budget. Local
    models often outlive that (sync to_thread does not always abort mid-read) —
    run-b6f2abb608bf ~337s / run-870f0cf94fb9 ~359s with declare=180; ``ev_to+90``
    orphaned at 270s mid-skill. Use +180 slack and never sit below global floor.

    Without a declared per-call timeout, keep ``fallback``.
    """
    fb = float(fallback)
    if not isinstance(event, dict):
        return fb
    raw = event.get("timeout_seconds")
    if raw is None:
        args = event.get("args") if isinstance(event.get("args"), dict) else {}
        raw = args.get("timeout_seconds")
    try:
        ev_to = float(raw or 0)
    except Exception:
        ev_to = 0.0
    if ev_to <= 0:
        return fb
    # Backup after declared wait_for, but never below global floor.
    return max(fb, float(ev_to) + 180.0)


def agent_stream_timeout_seconds(max_steps: int = 10) -> float:
    """Orphan / status-poll wall for workspace agent stream executes.

    Agent ReAct may nest skill LLM calls; default skill orphan wall (360s) is too
    short. Budget ≈ max_steps × LLM timeout × 1.25, clamped by env floors/ceilings.
    Stored on execution ``metadata.timeout`` so orphan_watchdog uses ``mt + 45``.
    """
    llm_to = llm_timeout_seconds()
    steps = max(1, int(max_steps or 10))
    try:
        floor = float(os.getenv("AIPLAT_AGENT_STREAM_ORPHAN_SECONDS", "1200") or "1200")
    except Exception:
        floor = 1200.0
    try:
        ceil = float(os.getenv("AIPLAT_AGENT_STREAM_ORPHAN_MAX_SECONDS", "2400") or "2400")
    except Exception:
        ceil = 2400.0
    if ceil < floor:
        ceil = floor
    # Prefer stall floor over bare LLM wait_for — local Agent runs often need
    # 2+ generates (reason → skill → DONE) each approaching the stall budget.
    per_step = max(max(30.0, llm_to) * 1.25, llm_generate_stall_seconds() * 0.85)
    raw = float(steps) * per_step
    return max(floor, min(ceil, raw))


def resolve_workspace_agent_model_purpose(agent_info: Any) -> str:
    """Purpose for workspace Agent ``model: auto`` (must match audit / llm_profile).

    Prefer AGENT.md ``skill_model_purpose``; else ReAct-like ``loop_type`` → agent;
    else agent_type map; default chat.
    """
    meta = getattr(agent_info, "metadata", None)
    if not isinstance(meta, dict):
        meta = {}
    purpose = str(meta.get("skill_model_purpose") or "").strip()
    if purpose:
        return purpose
    cfg = getattr(agent_info, "config", None)
    if isinstance(cfg, dict):
        purpose = str(cfg.get("skill_model_purpose") or "").strip()
        if purpose:
            return purpose
    loop_type = str(getattr(agent_info, "loop_type", None) or meta.get("loop_type") or "").strip().lower()
    if loop_type in ("react", "plan", "plan_execute", "function_call"):
        return "agent"
    agent_type = str(getattr(agent_info, "agent_type", None) or meta.get("agent_type") or "").strip().lower()
    return {
        "rag": "chat",
        "react": "agent",
        "conversational": "chat",
        "wiki_curator": "chat",
        "materials_chat": "chat",
        "plan_execute": "agent",
        "function_call": "agent",
    }.get(agent_type, "chat")


def resolve_skill_model_purpose(skill: Any, *, default: str = "skill_execution") -> str:
    """Purpose for Skill LLM binding from SKILL.md ``skill_model_purpose`` metadata."""
    cfg = getattr(skill, "_config", None)
    if cfg is None and hasattr(skill, "get_config"):
        try:
            cfg = skill.get_config()
        except Exception:
            cfg = None
    meta = getattr(cfg, "metadata", None) if cfg is not None else None
    if not isinstance(meta, dict):
        meta = {}
    purpose = str(meta.get("skill_model_purpose") or "").strip()
    if purpose:
        return purpose
    if cfg is not None:
        purpose = str(getattr(cfg, "skill_model_purpose", None) or "").strip()
        if purpose:
            return purpose
    return str(default or "skill_execution")


def persist_startable_scaffold_delivery(
    *,
    run_id: str,
    input_text: str,
    output_text: str,
) -> Dict[str, Any]:
    """Write startable-scaffold ``## FILE`` bodies to a run workspace on disk.

    Isolated coding slices are unchanged (observe-only). Gate is task-shaped
    (``_input_asks_startable_scaffold`` / FastAPI+Vite FILE list), not ``agent_id``.
    """
    info: Dict[str, Any] = {"disk_persist": "skip"}
    try:
        from core.management.execution_quality_review import (
            _delivery_looks_startable_scaffold,
            _input_asks_isolated_coding_slice,
            _input_asks_startable_scaffold,
        )
        from core.harness.utils.inline_autoreview_workspace import (
            extract_file_sections,
            persist_inline_delivery,
            resolve_run_persist_root,
        )
    except Exception:
        return {"disk_persist": "fail", "persist_error": "import"}

    isolated = _input_asks_isolated_coding_slice(input_text)
    startable = (not isolated) and (
        _input_asks_startable_scaffold(input_text)
        or _delivery_looks_startable_scaffold(output_text)
    )
    if not startable:
        return info
    if not extract_file_sections(output_text):
        return {"disk_persist": "missing", "persist_error": "no_file_sections"}
    try:
        root = resolve_run_persist_root(run_id)
        result = persist_inline_delivery(output_text, root)
    except Exception as exc:
        return {"disk_persist": "fail", "persist_error": str(exc)[:300]}
    files = result.get("files") if isinstance(result, dict) else []
    root_s = str((result or {}).get("root") or "")
    if result.get("ok") and files:
        return {
            "disk_persist": "ok",
            "persisted_root": root_s,
            "persisted_files": list(files),
        }
    return {
        "disk_persist": "fail" if result.get("error") else "missing",
        "persisted_root": root_s,
        "persisted_files": list(files or []),
        "persist_error": str(result.get("error") or "persist_failed")[:300],
    }


async def finalize_agent_after_skill_delivery(
    *,
    run_id: str,
    agent_id: str,
    output_text: str,
    start_time: Optional[float] = None,
    trace_id: str = "",
    metadata_extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Persist Agent row + RunGraph as completed right after delivery/auto_done.

    Why: ReAct may set LoopState FINISHED and emit ``skill_delivery_once`` / ``auto_done``,
    then hang in POST_LOOP / SECI / other teardown before
    ``_execute_workspace_agent_background`` reaches its normal upsert. UI stays
    「执行中」with a finished trajectory (canvas green, top badge still running).

    Idempotent: if the row is already terminal with non-empty output, returns True
    without wiping it.
    """
    import logging
    import time as _time

    rid = str(run_id or "").strip()
    aid = str(agent_id or "").strip() or "unknown"
    body = coerce_coding_delivery_text(str(output_text or "").strip())
    if not rid or len(body) < 20:
        return False

    # Refuse to seal a pending skill_call/tool_call JSON as a finished product.
    if looks_like_pending_action_envelope(body):
        logging.getLogger(__name__).info(
            "finalize delivery: pending action envelope → skip seal run_id=%s", rid
        )
        return False

    # Refuse to seal clarify / thin ## FILE / model-error as skill_delivery success.
    existing: Dict[str, Any] = {}
    try:
        from core.services.execution_store import get_execution_store as _ges0

        _ex0 = await _ges0().get_agent_execution(rid)
        if isinstance(_ex0, dict):
            existing = _ex0
    except Exception:
        existing = {}

    persist_in = ""
    in_payload = existing.get("input") if existing else None
    if isinstance(in_payload, dict):
        persist_in = str(
            in_payload.get("message")
            or in_payload.get("user_requirement")
            or in_payload.get("input")
            or ""
        )
    elif isinstance(in_payload, str):
        persist_in = in_payload
    if not str(persist_in or "").strip() and isinstance(metadata_extra, dict):
        persist_in = str(
            metadata_extra.get("user_task")
            or metadata_extra.get("_user_task")
            or ""
        )
    persist_info = persist_startable_scaffold_delivery(
        run_id=rid, input_text=persist_in, output_text=body
    )
    persist_raw: Dict[str, Any] = {"text": body}
    if persist_info.get("persisted_root"):
        persist_raw["persisted_root"] = persist_info["persisted_root"]
    if persist_info.get("persisted_files"):
        persist_raw["persisted_files"] = persist_info["persisted_files"]

    try:
        from core.management.execution_quality_review import is_non_deliverable_coding_output

        _in = persist_in
        if is_non_deliverable_coding_output(
            input_text=_in,
            output_text=body,
            raw_out=persist_raw,
            scope="skill",
        ):
            logging.getLogger(__name__).info(
                "finalize delivery: non-deliverable coding output → failed run_id=%s", rid
            )
            try:
                from core.services.execution_store import get_execution_store as _ges2

                store2 = _ges2()
                now_f = _time.time()
                t0_f = float(start_time or existing.get("start_time") or now_f)
                meta_f: Dict[str, Any] = {}
                if isinstance(existing.get("metadata"), dict):
                    meta_f.update(existing["metadata"])
                meta_f.update(
                    {
                        "skill_delivery_finalize": True,
                        "quality_block_completed": True,
                        "orphan_reason": "non_deliverable_coding_output",
                    }
                )
                meta_f.update(persist_info)
                if isinstance(metadata_extra, dict):
                    meta_f.update(metadata_extra)
                await store2.upsert_agent_execution(
                    {
                        "id": rid,
                        "agent_id": aid,
                        "status": "failed",
                        "input": existing.get("input"),
                        "output": persist_raw,
                        "error": (
                            "non-deliverable coding output "
                            "(thin stub / clarification / model runtime error)"
                        ),
                        "start_time": t0_f,
                        "end_time": now_f,
                        "duration_ms": max(0, int((now_f - t0_f) * 1000)),
                        "trace_id": str(trace_id or existing.get("trace_id") or ""),
                        "metadata": meta_f,
                    }
                )
                try:
                    from core.harness.observation.run_graph import mark_run_done

                    await mark_run_done(rid, status="failed")
                except Exception:
                    logging.getLogger(__name__).debug(
                        "finalize non-deliverable mark_run_done skip", exc_info=True
                    )
                if hasattr(store2, "close_running_syscall_events"):
                    try:
                        await store2.close_running_syscall_events(
                            rid,
                            status="failed",
                            error="non_deliverable_coding_output",
                        )
                    except Exception:
                        logging.getLogger(__name__).debug(
                            "finalize non-deliverable close syscalls skip",
                            exc_info=True,
                        )
                return True  # row sealed as failed
            except Exception:
                logging.getLogger(__name__).warning(
                    "finalize non-deliverable upsert failed run_id=%s", rid, exc_info=True
                )
                return False
    except Exception:
        logging.getLogger(__name__).debug(
            "finalize delivery substance check skipped", exc_info=True
        )

    try:
        from core.services.execution_store import get_execution_store

        store = get_execution_store()
    except Exception:
        logging.getLogger(__name__).debug("finalize delivery: no store", exc_info=True)
        return False

    now = _time.time()
    if not existing:
        try:
            got = await store.get_agent_execution(rid) if hasattr(store, "get_agent_execution") else None
            if isinstance(got, dict):
                existing = got
        except Exception:
            existing = {}

    prev_st = str(existing.get("status") or "").lower()
    prev_out = existing.get("output")
    prev_text = ""
    if isinstance(prev_out, str):
        prev_text = prev_out.strip()
    elif isinstance(prev_out, dict):
        prev_text = str(prev_out.get("text") or prev_out.get("output") or "").strip()

    persist_text = body if len(body) >= 20 else (prev_text or body)
    if persist_text != body:
        persist_info = persist_startable_scaffold_delivery(
            run_id=rid, input_text=persist_in, output_text=persist_text
        )

    if prev_st in ("completed", "ok", "success", "done") and len(prev_text) >= 20:
        # Already finalized — still persist startable scaffold if missing.
        prev_meta = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
        already_ok = str(prev_meta.get("disk_persist") or "") == "ok"
        if persist_info.get("disk_persist") == "ok" and not already_ok:
            try:
                meta_p = dict(prev_meta)
                meta_p.update(persist_info)
                if isinstance(metadata_extra, dict):
                    meta_p.update(metadata_extra)
                out_p: Dict[str, Any] = {"text": prev_text}
                if persist_info.get("persisted_root"):
                    out_p["persisted_root"] = persist_info["persisted_root"]
                if persist_info.get("persisted_files"):
                    out_p["persisted_files"] = persist_info["persisted_files"]
                await store.upsert_agent_execution(
                    {
                        "id": rid,
                        "agent_id": aid,
                        "status": existing.get("status") or "completed",
                        "input": existing.get("input"),
                        "output": out_p,
                        "error": existing.get("error"),
                        "start_time": existing.get("start_time"),
                        "end_time": existing.get("end_time"),
                        "duration_ms": existing.get("duration_ms"),
                        "trace_id": str(trace_id or existing.get("trace_id") or ""),
                        "metadata": meta_p,
                    }
                )
            except Exception:
                logging.getLogger(__name__).debug(
                    "finalize delivery persist-on-completed skipped", exc_info=True
                )
        try:
            from core.harness.observation.run_graph import mark_run_done

            await mark_run_done(rid, status="completed")
        except Exception:
            logging.getLogger(__name__).debug("finalize delivery mark_run_done skip", exc_info=True)
        try:
            closer = getattr(store, "close_running_syscall_events", None)
            if closer is not None:
                maybe = closer(rid, status="ok", error=None)
                if hasattr(maybe, "__await__"):
                    await maybe
        except Exception:
            logging.getLogger(__name__).debug(
                "finalize delivery close leftover syscalls skip", exc_info=True
            )
        return True

    # Also refuse green seal if already failed with substance
    if prev_st in ("failed", "error", "timeout") and existing.get("metadata", {}).get("quality_block_completed"):
        return True

    t0 = float(start_time or existing.get("start_time") or now)
    duration_ms = max(0, int((now - t0) * 1000))
    meta: Dict[str, Any] = {}
    if isinstance(existing.get("metadata"), dict):
        meta.update(existing["metadata"])
    meta.update(
        {
            "stream": True,
            "skill_delivery_finalize": True,
            "orphan_reason": "finalize_after_skill_delivery",
        }
    )
    if isinstance(metadata_extra, dict):
        meta.update(metadata_extra)

    meta.update(persist_info)

    out_payload: Dict[str, Any] = {"text": body}
    if persist_info.get("persisted_root"):
        out_payload["persisted_root"] = persist_info["persisted_root"]
    if persist_info.get("persisted_files"):
        out_payload["persisted_files"] = persist_info["persisted_files"]
    final_status = "completed"
    final_error = ""
    skip_qr = bool(
        isinstance(metadata_extra, dict)
        and (
            metadata_extra.get("orphan_watchdog")
            or str(metadata_extra.get("finalize_source") or "") == "status_orphan_watch"
        )
    )
    # Leave 「执行中」as soon as the product exists. QR / RunGraph / leftover
    # syscall close can stall on SQLite; a hung review must not keep the row running
    # (qa_agent run-124d89d5ef3f: auto_done ok, Agent still running).
    try:
        await store.upsert_agent_execution(
            {
                "id": rid,
                "agent_id": aid,
                "status": final_status,
                "input": existing.get("input"),
                "output": out_payload,
                "error": final_error,
                "start_time": t0,
                "end_time": now,
                "duration_ms": duration_ms,
                "trace_id": str(trace_id or existing.get("trace_id") or ""),
                "metadata": meta,
            }
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "finalize delivery upsert failed run_id=%s", rid, exc_info=True
        )
        return False

    try:
        if skip_qr:
            raise RuntimeError("skip_quality_review_orphan_watch")
        from core.management.execution_quality_review import (
            ensure_architecture_section_fields,
            ensure_architecture_rollout_weeks,
            sanitize_architecture_third_party,
            review_execution_output,
            quality_review_blocks_success,
            _unwrap_output as _eq_unwrap,
            _input_text as _eq_input_text,
        )
        import json as _json

        unwrapped = _eq_unwrap(out_payload)
        _eq_in = _eq_input_text(existing.get("input"))
        normed = ensure_architecture_section_fields(unwrapped)
        normed = ensure_architecture_rollout_weeks(normed, _eq_in)
        normed = sanitize_architecture_third_party(normed, _eq_in)
        if isinstance(normed, dict) and normed != unwrapped:
            out_payload = {"text": _json.dumps(normed, ensure_ascii=False)}
            body = out_payload["text"]
            if persist_info.get("persisted_root"):
                out_payload["persisted_root"] = persist_info["persisted_root"]
            if persist_info.get("persisted_files"):
                out_payload["persisted_files"] = persist_info["persisted_files"]
        # Skill trace + binding hints so autoreview_incomplete / language gates fire.
        skill_trace: list = []
        skill_names: list = []
        try:
            import asyncio as _aio_qr_ev

            ev = await _aio_qr_ev.wait_for(
                store.list_syscall_events(run_id=rid, limit=80),
                timeout=2.0,
            )
            items = (ev or {}).get("items") if isinstance(ev, dict) else (ev or [])
            if isinstance(items, list):
                for row in items:
                    if not isinstance(row, dict):
                        continue
                    kind = str(row.get("kind") or "").lower()
                    name = str(row.get("name") or "").strip()
                    if kind in ("skill",) or name in (
                        "code_generation",
                        "autoreview",
                        "code_review",
                        "code-hygiene",
                        "file_operations",
                    ):
                        skill_trace.append(
                            {
                                "kind": kind or "skill",
                                "name": name,
                                "status": str(row.get("status") or ""),
                            }
                        )
                        if name:
                            skill_names.append(name)
        except Exception:
            skill_trace = []
        hint_parts = [aid]
        for k in ("bound_skills", "required_skills", "skill_hint"):
            v = meta.get(k)
            if isinstance(v, (list, tuple)):
                hint_parts.extend(str(x) for x in v if str(x).strip())
            elif isinstance(v, str) and v.strip():
                hint_parts.append(v)
        if meta.get("coding_veto_exhausted") or meta.get("_coding_veto_exhausted"):
            hint_parts.append("followup exhausted")
        if isinstance(metadata_extra, dict):
            for k in ("bound_skills", "required_skills", "skill_hint"):
                v = metadata_extra.get(k)
                if isinstance(v, (list, tuple)):
                    hint_parts.extend(str(x) for x in v if str(x).strip())
                elif isinstance(v, str) and v.strip():
                    hint_parts.append(v)
            if metadata_extra.get("coding_veto_exhausted"):
                hint_parts.append("followup exhausted")
        hint_parts.extend(skill_names)
        # Frontend/coding agents almost always bind autoreview — include when exhausted.
        if "followup exhausted" in " ".join(hint_parts) and "autoreview" not in " ".join(hint_parts).lower():
            hint_parts.append("autoreview")
        dp = str(persist_info.get("disk_persist") or "").strip()
        if dp:
            hint_parts.append(f"disk_persist={dp}")
        qr = review_execution_output(
            kind="agent",
            asset_id=aid,
            asset_name=aid,
            input_payload=existing.get("input"),
            output=out_payload,
            status="completed",
            hints=" ".join(dict.fromkeys(p for p in hint_parts if p)),
            skill_trace=skill_trace,
            execution_id=rid,
        )
        meta["quality_review"] = qr
        if quality_review_blocks_success(qr):
            # Do not greenwash thin/clarify stubs as completed (same as loop veto).
            final_status = "failed"
            final_error = str(
                (qr.get("headline") if isinstance(qr, dict) else None)
                or "coding deliverable failed quality review (thin_code_stub/clarification_only)"
            )
            meta["quality_block_completed"] = True
            logging.getLogger(__name__).info(
                "finalize delivery blocked by quality_review run_id=%s verdict=%s",
                rid,
                (qr or {}).get("verdict") if isinstance(qr, dict) else None,
            )
    except Exception:
        logging.getLogger(__name__).debug("finalize delivery QR skipped", exc_info=True)

    if final_status != "completed" or meta.get("quality_review"):
        try:
            await store.upsert_agent_execution(
                {
                    "id": rid,
                    "agent_id": aid,
                    "status": final_status,
                    "input": existing.get("input"),
                    "output": out_payload,
                    "error": final_error,
                    "start_time": t0,
                    "end_time": now,
                    "duration_ms": duration_ms,
                    "trace_id": str(trace_id or existing.get("trace_id") or ""),
                    "metadata": meta,
                }
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "finalize delivery QR upsert failed run_id=%s", rid, exc_info=True
            )

    import asyncio as _aio_fin_tail

    async def _seal_graph_and_leftovers() -> None:
        from core.harness.observation.run_graph import (
            close_node,
            open_node,
            mark_run_done,
        )

        await close_node(
            rid,
            f"agent:{aid}:start",
            status="ok" if final_status == "completed" else "error",
            result={"text": body[:5000]},
            duration_ms=duration_ms,
            audit=True,
        )
        await open_node(
            rid,
            f"agent:{aid}:end",
            kind="agent",
            name="agent_end",
            parent_id=f"agent:{aid}:start",
            label="完成" if final_status == "completed" else "失败",
            role="work",
            audit=True,
        )
        await close_node(
            rid,
            f"agent:{aid}:end",
            status="ok" if final_status == "completed" else "error",
            result={"text": body[:5000]},
            duration_ms=duration_ms,
            audit=True,
        )
        await mark_run_done(rid, status=final_status)
        closer = getattr(store, "close_running_syscall_events", None)
        if closer is not None:
            seal_st = "ok" if final_status == "completed" else "error"
            maybe = closer(
                rid,
                status=seal_st,
                error=final_error or None,
                error_code="FINALIZE_LEFTOVER" if final_status != "completed" else None,
            )
            if hasattr(maybe, "__await__"):
                await maybe
        if hasattr(store, "append_run_event"):
            await store.append_run_event(
                run_id=rid,
                event_type="run_end",
                trace_id=str(trace_id or existing.get("trace_id") or "") or None,
                tenant_id=None,
                payload={
                    "kind": "agent",
                    "agent_id": aid,
                    "status": final_status,
                    "duration_ms": duration_ms,
                    "source": "skill_delivery_finalize",
                },
            )

    try:
        await _aio_fin_tail.wait_for(_seal_graph_and_leftovers(), timeout=4.0)
    except Exception:
        logging.getLogger(__name__).debug(
            "finalize delivery graph/leftover seal skipped run_id=%s",
            rid,
            exc_info=True,
        )

    return True


def looks_like_pending_action_envelope(text: str) -> bool:
    """True when body is still a skill_call/tool_call intent — not a finished product.

    Weak models often emit ``{"type":"skill_call","skill":"code_generation",...}`` as
    the final answer. Sealing that as completed greenwashes a call that never ran.
    """
    raw = str(text or "").strip()
    if not raw or raw[:1] not in "{[":
        return False
    try:
        import json as _json

        obj = _json.loads(raw)
    except Exception:
        # Truncated / commentary — heuristic for common envelopes
        low = raw[:240].lower()
        return '"type"' in low and (
            '"skill_call"' in low or '"tool_call"' in low or '"action_call"' in low
        )
    if not isinstance(obj, dict):
        return False
    typ = str(obj.get("type") or "").strip().lower()
    if typ in ("skill_call", "tool_call", "action_call", "function_call"):
        return True
    # Structured call without type tag still means "invoke me", not deliverable
    if typ in ("", "call", "action") and (
        (isinstance(obj.get("skill"), str) and obj.get("skill"))
        or (isinstance(obj.get("skill_name"), str) and obj.get("skill_name"))
        or (isinstance(obj.get("tool"), str) and obj.get("tool"))
        or (isinstance(obj.get("tool_name"), str) and obj.get("tool_name"))
    ):
        # Exclude done-style envelopes that happen to include a skill field
        if obj.get("answer") or obj.get("output") or typ == "done":
            return False
        return True
    return False


def extract_skill_delivery_answer(event: Dict[str, Any]) -> str:
    """Pull answer text from a skill_delivery_once / done syscall or graph node."""
    if not isinstance(event, dict):
        return ""
    result = event.get("result")
    if result is None and event.get("result_json"):
        try:
            import json as _json

            result = _json.loads(str(event.get("result_json") or "{}"))
        except Exception:
            result = None
    if isinstance(result, dict):
        for k in ("answer", "output", "text", "body"):
            v = result.get(k)
            if isinstance(v, str) and len(v.strip()) >= 20:
                if looks_like_pending_action_envelope(v):
                    continue
                return v.strip()
            if isinstance(v, dict):
                try:
                    import json as _json

                    dumped = _json.dumps(v, ensure_ascii=False)
                except Exception:
                    dumped = str(v)
                if looks_like_pending_action_envelope(dumped):
                    continue
                return dumped
        # nested output dict from skill
        out = result.get("output")
        if isinstance(out, dict):
            try:
                import json as _json

                dumped = _json.dumps(out, ensure_ascii=False)
            except Exception:
                dumped = str(out)
            if not looks_like_pending_action_envelope(dumped):
                return dumped
    if isinstance(result, str) and len(result.strip()) >= 20:
        if looks_like_pending_action_envelope(result):
            return ""
        return result.strip()
    return ""


_FOLLOWUP_SKILL_IDS = frozenset({"autoreview", "code_review", "code-hygiene"})
_CODING_PRIMARY_SKILL_IDS = frozenset(
    {"code_generation", "code-hygiene", "file_operations"}
)


def resolve_bound_skill_ids(state: Any, skills: Any = None) -> List[str]:
    """Agent ``required_skills`` for HITL waiver and coding follow-up gates.

    Prefer ``state.context['_bound_skill_ids']`` (set by CoreFacade / StageRunner).
    Fall back to injected skill object names. Never match on agent_id.
    """
    ctx: Any = None
    if isinstance(state, dict):
        ctx = state.get("context") if isinstance(state.get("context"), dict) else state
    else:
        ctx = getattr(state, "context", None)
    raw: Any = None
    if isinstance(ctx, dict):
        raw = ctx.get("_bound_skill_ids")
    if not (isinstance(raw, (list, tuple, set)) and raw):
        raw = []
        for sk in skills or []:
            name = getattr(sk, "name", None)
            if not name:
                cfg = getattr(sk, "_config", None)
                name = getattr(cfg, "name", None) if cfg is not None else None
            n = str(name or "").strip()
            if n:
                raw.append(n)
    out: List[str] = []
    seen = set()
    for x in raw:
        n = str(x or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def orphan_skill_delivery_answer(items: Any) -> str:
    """Answer body for status-orphan seal — only after the loop declared delivery done.

    Do **not** seal merely because a skill succeeded (run-073bd173ac06): coding Agents
    with ``skill_delivery=once`` still need bound follow-ups (``autoreview`` etc.) before
    observe emits ``skill_delivery_once``. Sealing mid-loop skips that review step.

    Ready when ``skill_delivery_once`` exists, **or** conversational ``auto_done`` with
    a real answer and no coding-primary skill in the same run (qa_agent / PM: POST_LOOP
    hang after auto_done left the row ``running`` — run-124d89d5ef3f). Premature
    coding ``auto_done`` without ``skill_delivery_once`` still returns empty.
    """
    rows = items if isinstance(items, list) else []
    has_delivery_once = False
    has_auto_done = False
    coding_primary_ok = False
    delivery_answer = ""
    auto_answer = ""
    skill_answer = ""
    skill_success: set[str] = set()
    skill_running: set[str] = set()
    for it in rows:
        if not isinstance(it, dict):
            continue
        nm = str(it.get("name") or "").lower()
        kind_i = str(it.get("kind") or "").lower()
        st = str(it.get("status") or "").lower()
        if kind_i == "done" and nm == "skill_delivery_once":
            has_delivery_once = True
            cand = extract_skill_delivery_answer(it)
            if len(cand) > len(delivery_answer):
                delivery_answer = cand
        if kind_i == "done" and nm == "auto_done" and st in (
            "ok",
            "success",
            "completed",
            "done",
        ):
            has_auto_done = True
            cand = extract_skill_delivery_answer(it)
            if len(cand) > len(auto_answer):
                auto_answer = cand
        if kind_i == "skill":
            if st in ("ok", "success", "completed", "done"):
                skill_success.add(nm)
                if nm in _CODING_PRIMARY_SKILL_IDS:
                    coding_primary_ok = True
                if nm in _FOLLOWUP_SKILL_IDS:
                    continue
                cand = extract_skill_delivery_answer(it)
                if len(cand) > len(skill_answer):
                    skill_answer = cand
            elif st == "running":
                skill_running.add(nm)

    def _pick(primary: str, skill: str) -> str:
        if len(skill) >= 40 and (len(skill) >= len(primary) or len(primary) < 40):
            return skill
        return primary if len(primary) >= 40 else ""

    if has_delivery_once:
        return _pick(delivery_answer, skill_answer)

    # Unique in-flight skill (running with no success twin) → still working.
    if any(n and n not in skill_success for n in skill_running):
        return ""
    if not has_auto_done:
        return ""
    if coding_primary_ok:
        return ""
    body = _pick(auto_answer, skill_answer)
    if body and looks_like_pending_action_envelope(body):
        return ""
    return body


def agent_no_progress_seconds() -> float:
    """How long an Agent may stay on agent_start with zero llm/skill/tool syscalls."""
    try:
        return float(os.getenv("AIPLAT_AGENT_NO_PROGRESS_SECONDS", "90") or "90")
    except Exception:
        return 90.0


def count_progress_syscalls(items: Any) -> int:
    """Count syscalls that prove ReAct left the agent_start gate."""
    n = 0
    for it in items or []:
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
            n += 1
    return n


async def mark_agent_no_progress_timeout(
    *,
    run_id: str,
    agent_id: str = "",
    start_time: Optional[float] = None,
    input_payload: Any = None,
    trace_id: str = "",
    source: str = "agent_no_progress_watch",
) -> bool:
    """Persist timeout when Agent never left agent_start (0 progress syscalls).

    Used by API-loop early watch (survives hung bg thread) and status orphan probe.
    """
    import logging
    import time as _time

    rid = str(run_id or "").strip()
    if not rid:
        return False
    try:
        from core.services.execution_store import get_execution_store

        store = get_execution_store()
    except Exception:
        logging.getLogger(__name__).debug("no_progress: no store", exc_info=True)
        return False

    existing: Dict[str, Any] = {}
    try:
        got = await store.get_agent_execution(rid) if hasattr(store, "get_agent_execution") else None
        if isinstance(got, dict):
            existing = got
    except Exception:
        existing = {}

    prev = str(existing.get("status") or "").lower()
    if prev and prev not in ("running", "accepted", "started", "pending", ""):
        return True  # already terminal

    t0 = float(start_time or existing.get("start_time") or _time.time())
    age = max(0.0, _time.time() - t0)
    aid = str(agent_id or existing.get("agent_id") or "unknown")
    err = (
        f"{source}: stuck at agent_start only (0 llm/skill/tool) for {int(age)}s; "
        f"background never reached first LLM; marked timeout"
    )
    meta: Dict[str, Any] = {}
    if isinstance(existing.get("metadata"), dict):
        meta.update(existing["metadata"])
    meta.update(
        {
            "orphan_watchdog": True,
            "orphan_reason": "no_progress",
            "agent_no_progress_watch": True,
            "no_progress_source": source,
        }
    )
    try:
        await store.upsert_agent_execution(
            {
                "id": rid,
                "agent_id": aid,
                "status": "timeout",
                "error": err,
                "end_time": _time.time(),
                "duration_ms": int(age * 1000),
                "input": input_payload if input_payload is not None else existing.get("input"),
                "output": existing.get("output"),
                "start_time": t0,
                "trace_id": str(trace_id or existing.get("trace_id") or ""),
                "metadata": meta,
            }
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "no_progress upsert failed run_id=%s", rid, exc_info=True
        )
        return False

    try:
        if hasattr(store, "close_running_syscall_events"):
            await store.close_running_syscall_events(
                rid,
                status="timeout",
                error=err,
                error_code="AGENT_NO_PROGRESS",
            )
    except Exception:
        logging.getLogger(__name__).debug("no_progress close syscalls failed", exc_info=True)

    try:
        from core.harness.observation.run_graph import close_node, mark_run_done

        await close_node(
            rid,
            f"agent:{aid}:start",
            status="error",
            error=err,
            audit=False,
        )
        await mark_run_done(rid, status="timeout")
    except Exception:
        logging.getLogger(__name__).debug("no_progress graph close failed", exc_info=True)

    return True


async def watch_agent_no_progress(
    *,
    run_id: str,
    agent_id: str = "",
    start_time: Optional[float] = None,
    input_payload: Any = None,
    trace_id: str = "",
    cancel_cb: Optional[Any] = None,
    source: str = "agent_no_progress_watch",
) -> None:
    """Sleep then timeout the Agent if still at agent_start with zero progress."""
    import asyncio
    import logging

    delay = max(30.0, agent_no_progress_seconds())
    try:
        await asyncio.sleep(delay)
    except Exception:
        return

    rid = str(run_id or "").strip()
    if not rid:
        return
    try:
        from core.services.execution_store import get_execution_store

        store = get_execution_store()
        got = await store.get_agent_execution(rid) if hasattr(store, "get_agent_execution") else None
        if isinstance(got, dict):
            st = str(got.get("status") or "").lower()
            if st and st not in ("running", "accepted", "started", "pending"):
                return
        ev = await store.list_syscall_events(run_id=rid, limit=80)
        items = (ev or {}).get("items") if isinstance(ev, dict) else (ev or [])
        if count_progress_syscalls(items) > 0:
            return
        ok = await mark_agent_no_progress_timeout(
            run_id=rid,
            agent_id=agent_id,
            start_time=start_time,
            input_payload=input_payload,
            trace_id=trace_id,
            source=source,
        )
        if ok and cancel_cb is not None:
            try:
                cancel_cb()
            except Exception:
                logging.getLogger(__name__).debug("no_progress cancel_cb failed", exc_info=True)
    except Exception:
        logging.getLogger(__name__).debug(
            "watch_agent_no_progress failed run_id=%s", rid, exc_info=True
        )


_SKILL_BLURB_MARKERS = (
    "根据PRD需求设计",
    "输出结构化JSON",
    "触发条件",
    "跳过条件",
    "纯文本需求",
    "必须先调用",
    "实质交付后调用",
    "禁止空转重复调用",
    "skill_delivery",
    "使用 ## FILE",
    "根据 Architecture 中的 api_contracts",
)

# Tokens that distinguish a real user brief from a skill SOP blurb.
_USER_TASK_MARKERS = (
    "巡检",
    "报障",
    "不上公网",
    "钉钉",
    "6 周",
    "6周",
    "分期",
    "看板",
    "派修",
    "TypeScript",
    "typescript",
    "/api/",
    "endpoints:",
    "api_contracts:",
)


def skill_arg_payload_is_thin(val: str, user_task: str) -> bool:
    """True when skill_call input is a SOP blurb / stub, not the user brief."""
    s = (val or "").strip()
    task = (user_task or "").strip()
    if len(s) < 80:
        return True
    if any(b in s for b in _SKILL_BLURB_MARKERS) and (
        len(s) < 400 or len(s) < len(task) * 0.6
    ):
        return True
    user_hits = [m for m in _USER_TASK_MARKERS if m in task]
    if user_hits and not any(m in s for m in user_hits):
        return True
    if len(task) >= 120 and len(s) < len(task) * 0.5:
        return True
    return False
