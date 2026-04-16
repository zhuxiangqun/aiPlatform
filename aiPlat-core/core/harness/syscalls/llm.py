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
from core.harness.kernel.execution_context import get_active_release_context, record_prompt_revision_application


Message = Dict[str, Any]


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
    if model is None or not hasattr(model, "generate"):
        raise RuntimeError("No model available for sys_llm_generate")

    # Phase 3: gates (best-effort, fail-open).
    trace_gate = TraceGate()
    ctx_gate = ContextGate()
    res_gate = ResilienceGate()

    prepared = ctx_gate.prepare_llm_args(prompt, context=trace_context or {})

    # Phase 4 (optional): central prompt assembly + prompt_version for replay/audit.
    prompt_version = None
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

            assembled = PromptAssembler().assemble(prepared)
            prepared = assembled.messages
            prompt_version = assembled.prompt_version
        except Exception:
            prompt_version = None
    _ar = get_active_release_context()
    span = await trace_gate.start(
        "sys.llm.generate",
        attributes={
            "has_trace_context": bool(trace_context),
            "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
            "prompt_version": prompt_version,
            # Phase 6.13: make prompt revision application observable at span level
            "active_release_candidate_id": _ar.candidate_id if _ar else None,
            "active_release_version": _ar.version if _ar else None,
            "applied_prompt_revision_ids": applied_prompt_revision_ids,
            "ignored_prompt_revision_ids": ignored_prompt_revision_ids,
            "prompt_revision_conflicts": prompt_revision_conflicts,
            "prompt_revision_strict": os.getenv("AIPLAT_PROMPT_REVISION_STRICT", "false").lower() in ("1", "true", "yes", "y"),
        },
    )
    start_ts = time.time()
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
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "llm",
                        "name": "generate",
                        "status": "success",
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"prompt_type": "messages" if isinstance(prepared, list) else "text"},
                        "result": {
                            "has_content": bool(getattr(result, "content", None)),
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
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"prompt_type": "messages" if isinstance(prepared, list) else "text"},
                        "error": "llm_error",
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
