"""
sys_llm - LLM syscall wrappers (Phase 2).

This module intentionally keeps behavior identical to direct adapter calls,
while providing a single choke point for future gates:
- TraceGate (span + token usage persistence)
- ResilienceGate (retry/timeout/fallback)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import os
import time

from core.harness.infrastructure.gates import TraceGate, ContextGate, ResilienceGate
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.execution_context import get_active_release_context, get_active_request_context, record_prompt_revision_application


Message = Dict[str, Any]

def _guard_messages(messages: List[Message]) -> tuple[List[Message], Dict[str, Any]]:
    """
    Guard + repair a chat transcript to reduce provider rejection and "orphan tool result" issues.

    - Unknown roles are converted to `system`
    - `tool` role is converted to `system` (aiPlat doesn't use native tool-role protocols)
    - Adjacent same-role messages are merged (keeps alternation stable)
    - Per-message content length is capped (env: AIPLAT_LLM_MESSAGE_MAX_CHARS)
    """
    max_chars = int(os.getenv("AIPLAT_LLM_MESSAGE_MAX_CHARS", "20000") or "20000")

    stats: Dict[str, Any] = {
        "input_count": len(messages or []),
        "output_count": 0,
        "converted_roles": 0,
        "merged_messages": 0,
        "truncated_messages": 0,
        "max_chars": max_chars,
    }

    if not messages:
        return [], stats

    def _norm_role(r: Any) -> str:
        r = str(r or "").strip().lower()
        if r in ("system", "user", "assistant"):
            return r
        if r == "tool":
            return "system"
        return "system"

    def _norm_content(c: Any) -> str:
        if c is None:
            return ""
        if not isinstance(c, str):
            try:
                c = str(c)
            except Exception:
                c = ""
        if max_chars > 0 and len(c) > max_chars:
            stats["truncated_messages"] += 1
            return c[: max(0, max_chars - 16)] + " …(truncated)"
        return c

    out: List[Message] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role0 = m.get("role", "user")
        role = _norm_role(role0)
        if role != str(role0 or "").strip().lower():
            stats["converted_roles"] += 1

        content = _norm_content(m.get("content", ""))
        if str(role0 or "").strip().lower() == "tool":
            # prevent "tool message without tool_call" provider errors
            content = "TOOL_RESULT:\n" + content

        if out and out[-1].get("role") == role and role != "system":
            # merge adjacent user/user or assistant/assistant (fail-open)
            out[-1]["content"] = (str(out[-1].get("content") or "") + "\n" + content).strip()
            stats["merged_messages"] += 1
        else:
            out.append({"role": role, "content": content})

    # Ensure system message at the front for provider compatibility.
    if out and out[0].get("role") != "system":
        out.insert(0, {"role": "system", "content": ""})
        stats["output_count"] = len(out)
    stats["output_count"] = len(out)
    return out, stats


async def sys_llm_generate(
    model: Any,
    prompt: Union[str, List[Message]],
    *,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Execute a model generation call.

    Args:
        model: LLM adapter instance (must provide async generate()).
        prompt: Either a string prompt or chat messages list.
        trace_context: Reserved for future tracing integration.
    """
    # Phase 3: gates (best-effort, fail-open).
    trace_gate = TraceGate()
    ctx_gate = ContextGate()
    res_gate = ResilienceGate()

    # Start span as early as possible so "fast-fail" (e.g. missing model)
    # still produces an observable span and audit record.
    span = await trace_gate.start(
        "sys.llm.generate",
        attributes={
            "has_trace_context": bool(trace_context),
            "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
        },
    )
    start_ts = time.time()
    _ar = get_active_release_context()
    _pr = get_active_request_context()

    if model is None or not hasattr(model, "generate"):
        end_ts = time.time()
        await trace_gate.end(span, success=False)
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "llm",
                        "name": "generate",
                        "status": "failed",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": getattr(_pr, "user_id", None),
                        "session_id": getattr(_pr, "session_id", None),
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"prompt_type": "messages" if isinstance(prompt, list) else "text"},
                        "error": "no_model",
                        "error_code": "NO_MODEL",
                    }
                )
            except Exception:
                pass
        raise RuntimeError("No model available for sys_llm_generate")

    prepared = ctx_gate.prepare_llm_args(prompt, context=trace_context or {})
    message_guard_stats: Optional[Dict[str, Any]] = None
    if isinstance(prepared, list):
        try:
            prepared, message_guard_stats = _guard_messages(prepared)
        except Exception:
            message_guard_stats = {"error": "message_guard_failed"}

    # PR-12: Tenant quotas (best-effort). Block when already over daily budget.
    try:
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        tid = getattr(_pr, "tenant_id", None)
        if store is not None and tid:
            quota_item = await store.get_tenant_quota(tenant_id=str(tid))
            quota = quota_item.get("quota") if isinstance(quota_item, dict) else {}
            daily = quota.get("daily") if isinstance(quota, dict) and isinstance(quota.get("daily"), dict) else {}
            lim_tokens = daily.get("llm_total_tokens")
            if lim_tokens is not None:
                try:
                    lim_i = int(lim_tokens)
                except Exception:
                    lim_i = None
                if lim_i is not None:
                    day = time.strftime("%Y-%m-%d", time.gmtime())
                    cur = await store.get_tenant_usage(tenant_id=str(tid), day=str(day), metric_key="llm_total_tokens")
                    if cur >= float(lim_i):
                        reason = f"tenant quota exceeded: llm_total_tokens {cur}/{lim_i} (day={day})"
                        try:
                            await store.add_syscall_event(
                                {
                                    "trace_id": span.trace_id,
                                    "span_id": getattr(span, "span_id", None),
                                    "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                                    "kind": "llm",
                                    "name": "generate",
                                    "status": "quota_exceeded",
                                    "target_type": _ar.target_type if _ar else None,
                                    "target_id": _ar.target_id if _ar else None,
                                    "tenant_id": str(tid),
                                    "user_id": getattr(_pr, "user_id", None),
                                    "session_id": getattr(_pr, "session_id", None),
                                    "start_time": start_ts,
                                    "end_time": start_ts,
                                    "duration_ms": 0.0,
                                    "args": {"prompt_type": "messages" if isinstance(prepared, list) else "text"},
                                    "error": reason,
                                    "error_code": "QUOTA_EXCEEDED",
                                }
                            )
                        except Exception:
                            pass
                        try:
                            await store.add_audit_log(
                                action="llm_quota_exceeded",
                                status="denied",
                                tenant_id=str(tid),
                                actor_id=str(getattr(_pr, "user_id", None) or "system"),
                                resource_type="llm",
                                resource_id=str(getattr(getattr(model, "config", None), "model", None) or getattr(model, "model", None) or "default"),
                                run_id=(trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                                trace_id=span.trace_id,
                                detail={"reason": reason, "day": day, "limit": lim_i, "current": cur},
                            )
                        except Exception:
                            pass
                        await trace_gate.end(span, success=False)
                        raise RuntimeError("quota_exceeded")
    except Exception:
        # fail-open if quota infra fails
        pass

    # Phase 4 (optional): central prompt assembly + prompt_version for replay/audit.
    prompt_version = None
    prompt_meta: Dict[str, Any] = {}
    applied_prompt_revision_ids: List[str] = []
    prompt_revision_conflicts: List[Dict[str, Any]] = []
    ignored_prompt_revision_ids: List[str] = []
    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
        try:
            from core.harness.assembly import PromptAssembler
            # Phase 6.8 (optional): apply published prompt revisions (behavior change, gated).
            if os.getenv("AIPLAT_APPLY_PROMPT_REVISIONS", "false").lower() in ("1", "true", "yes", "y"):
                try:
                    runtime = get_kernel_runtime()
                    store = getattr(runtime, "execution_store", None) if runtime else None
                    ctx = get_active_release_context()
                    if store is not None and ctx is not None:
                        from core.learning.apply import LearningApplier

                        applier = LearningApplier(store)
                        resolved = await applier.resolve_prompt_revision_patch(
                            target_type=ctx.target_type,
                            target_id=ctx.target_id,
                        )
                        patch = resolved.get("patch") if isinstance(resolved, dict) else {}
                        applied_prompt_revision_ids = resolved.get("artifact_ids") or []
                        prompt_revision_conflicts = resolved.get("conflicts") or []
                        ignored_prompt_revision_ids = resolved.get("ignored_artifact_ids") or []
                        if isinstance(patch, dict) and patch:
                            prepared = _apply_prompt_patch(prepared, patch)
                except Exception:
                    pass
            # Phase 6.12: aggregate audit info for the whole execution (best-effort).
            try:
                record_prompt_revision_application(
                    applied_ids=applied_prompt_revision_ids,
                    ignored_ids=ignored_prompt_revision_ids,
                    conflicts=prompt_revision_conflicts,
                )
            except Exception:
                pass

            # Provide target identity for prompt caching keys (Roadmap-1).
            _ctx = get_active_release_context()
            assembled = PromptAssembler().assemble(
                prepared,
                metadata={
                    "target_type": _ctx.target_type if _ctx else None,
                    "target_id": _ctx.target_id if _ctx else None,
                },
            )
            prepared = assembled.messages
            prompt_version = assembled.prompt_version
            prompt_meta = assembled.metadata or {}
        except Exception:
            prompt_version = None
    _ar = get_active_release_context()
    # Enrich span attributes after we know prompt_version / release context.
    try:
        runtime = get_kernel_runtime()
        trace_service = getattr(runtime, "trace_service", None) if runtime else None
        if trace_service and getattr(span, "span_id", None):
            await trace_service.add_span_event(
                span.span_id,
                "llm.prompt.info",
                attributes={
                    "prompt_version": prompt_version,
                    "active_release_candidate_id": _ar.candidate_id if _ar else None,
                    "active_release_version": _ar.version if _ar else None,
                    "applied_prompt_revision_ids": applied_prompt_revision_ids,
                    "ignored_prompt_revision_ids": ignored_prompt_revision_ids,
                    "prompt_revision_conflicts": prompt_revision_conflicts,
                    # ContextEngine / prompt stats (best-effort)
                    "context_engine": prompt_meta.get("context_engine") if isinstance(prompt_meta, dict) else None,
                    "prompt_message_count": prompt_meta.get("prompt_message_count") if isinstance(prompt_meta, dict) else None,
                    "prompt_estimated_tokens": prompt_meta.get("prompt_estimated_tokens") if isinstance(prompt_meta, dict) else None,
                    "project_context_file": prompt_meta.get("project_context_file") if isinstance(prompt_meta, dict) else None,
                    "project_context_sha256": prompt_meta.get("project_context_sha256") if isinstance(prompt_meta, dict) else None,
                    "project_context_blocked": prompt_meta.get("project_context_blocked") if isinstance(prompt_meta, dict) else None,
                    "workspace_context_hash": prompt_meta.get("workspace_context_hash") if isinstance(prompt_meta, dict) else None,
                    "stable_prompt_version": prompt_meta.get("stable_prompt_version") if isinstance(prompt_meta, dict) else None,
                    "stable_cache_key": prompt_meta.get("stable_cache_key") if isinstance(prompt_meta, dict) else None,
                    "stable_cache_hit": prompt_meta.get("stable_cache_hit") if isinstance(prompt_meta, dict) else None,
                    "stable_system_prompt_chars": prompt_meta.get("stable_system_prompt_chars") if isinstance(prompt_meta, dict) else None,
                    "ephemeral_overlay_chars": prompt_meta.get("ephemeral_overlay_chars") if isinstance(prompt_meta, dict) else None,
                    "session_search_hits": prompt_meta.get("session_search_hits") if isinstance(prompt_meta, dict) else None,
                },
            )
    except Exception:
        pass
    try:
        async def _call():
            return await model.generate(prepared)  # type: ignore[misc]

        retries = int(os.getenv("AIPLAT_LLM_RETRIES", "0") or "0")
        timeout_seconds = os.getenv("AIPLAT_LLM_TIMEOUT_SECONDS")
        timeout = float(timeout_seconds) if timeout_seconds else None
        result = await res_gate.run(_call, retries=retries, timeout_seconds=timeout)
        end_ts = time.time()
        await trace_gate.end(span, success=True)
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                # PR-12 usage ledger (best-effort)
                try:
                    tid = getattr(_pr, "tenant_id", None)
                    if tid:
                        usage = getattr(result, "usage", None)
                        if isinstance(usage, dict):
                            total = usage.get("total_tokens")
                            if total is None:
                                total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
                            total_f = float(total or 0)
                            if total_f > 0:
                                day = time.strftime("%Y-%m-%d", time.gmtime())
                                await store.add_tenant_usage(tenant_id=str(tid), metric_key="llm_total_tokens", amount=total_f, day=day)
                except Exception:
                    pass
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "llm",
                        "name": "generate",
                        "status": "success",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": getattr(_pr, "user_id", None),
                        "session_id": getattr(_pr, "session_id", None),
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {
                            "prompt_type": "messages" if isinstance(prepared, list) else "text",
                            "message_guard": message_guard_stats,
                        },
                        "result": {
                            "has_content": bool(getattr(result, "content", None)),
                            "usage": getattr(result, "usage", None) if isinstance(getattr(result, "usage", None), dict) else None,
                            "prompt_version": prompt_version,
                            "applied_prompt_revision_ids": applied_prompt_revision_ids,
                            "ignored_prompt_revision_ids": ignored_prompt_revision_ids,
                            "prompt_revision_conflicts": prompt_revision_conflicts,
                        },
                    }
                )
            except Exception:
                pass
        return result
    except Exception:
        end_ts = time.time()
        await trace_gate.end(span, success=False)
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "llm",
                        "name": "generate",
                        "status": "failed",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": getattr(_pr, "user_id", None),
                        "session_id": getattr(_pr, "session_id", None),
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"prompt_type": "messages" if isinstance(prepared, list) else "text"},
                        "error": "llm_error",
                        "error_code": "LLM_ERROR",
                        "result": {
                            "prompt_version": prompt_version,
                            "applied_prompt_revision_ids": applied_prompt_revision_ids,
                            "ignored_prompt_revision_ids": ignored_prompt_revision_ids,
                            "prompt_revision_conflicts": prompt_revision_conflicts,
                        },
                    }
                )
            except Exception:
                pass
        raise


def _apply_prompt_patch(prompt: Union[str, List[Message]], patch: Dict[str, Any]) -> Union[str, List[Message]]:
    """
    Apply prompt_revision patch to prompt.
    Supported patch keys:
      - prepend: str
      - append: str
    """
    prepend = patch.get("prepend")
    append = patch.get("append")
    if not isinstance(prepend, str):
        prepend = ""
    if not isinstance(append, str):
        append = ""

    if isinstance(prompt, str):
        text = prompt
        if prepend:
            text = prepend + "\n" + text
        if append:
            text = text + "\n" + append
        return text

    if isinstance(prompt, list) and prompt:
        # Patch the first user message, else first message.
        idx = 0
        for i, m in enumerate(prompt):
            if isinstance(m, dict) and m.get("role") == "user":
                idx = i
                break
        m = dict(prompt[idx]) if isinstance(prompt[idx], dict) else {"role": "user", "content": str(prompt[idx])}
        content = str(m.get("content", "") or "")
        if prepend:
            content = prepend + "\n" + content
        if append:
            content = content + "\n" + append
        m["content"] = content
        out = list(prompt)
        out[idx] = m
        return out

    return prompt
