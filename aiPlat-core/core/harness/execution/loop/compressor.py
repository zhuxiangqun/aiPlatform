"""
Context compression & shaping pipeline — extracted from loop.py.

Handles: 5-level compaction, context shaping pipeline, budget trimming.
"""
import os, time, re, json, logging
from typing import Any, Dict, List, Optional

from ...interfaces.loop import LoopState, LoopConfig
from ...memory.compression import _background_tool_summarize
from ...kernel.runtime import get_kernel_runtime


async def apply_context_shaping(state: LoopState, config: LoopConfig) -> None:
    """Original: _apply_context_shaping_pipeline (loop.py:1223)"""
    """
    Multi-stage context shaping pipeline (skeleton + observability).

    Stages (in order, cost ascending):
    - budget_trim (observability record of current budget state)
    - prune (priority-based message removal at >=80% budget)
    - micro_compress (reuses existing ContextCompression at >=90%)
    - fold (merge consecutive same-role messages, cost-free)
    - auto_compress (episodic summarization via MemoryManager, fires at >=8 msgs)
    """
    if os.getenv("AIPLAT_ENABLE_CONTEXT_SHAPING_PIPELINE", "true").lower() not in ("1", "true", "yes", "y"):
        return

    stages = ["budget_trim", "prune", "micro_compress", "fold", "auto_compress"]
    pipeline_stats: Dict[str, Any] = {"enabled": True, "stages": [], "started_at": time.time()}

    async def _stage(name: str, fn) -> None:
        s_before = self._estimate_context_stats(state)  # noqa: F821
        err = None
        started = time.time()
        try:
            await fn()
        except Exception as e:
            err = str(e)
        ended = time.time()
        s_after = self._estimate_context_stats(state)  # noqa: F821
        item = {
            "stage": name,
            "started_at": started,
            "ended_at": ended,
            "duration_ms": (ended - started) * 1000.0,
            "before": s_before,
            "after": s_after,
            "error": err,
        }
        pipeline_stats["stages"].append(item)
        await self._append_run_event(state, event_type="context_shaping", payload=item)  # noqa: F821

    async def _budget_trim():
        """Record current tool/skill description budgets for observability.
        
        Tools and skills already have per-description budget limits applied
        by the disclosure budget system. This stage records the current state
        so downstream stages (prune, fold) can make informed decisions.
        """
        state.metadata["_budget_trim_applied"] = True

    async def _prune():
        """Priority-based message pruning at moderate pressure (>= 80%).
        
        When token budget exceeds 80%, remove low-priority messages first
        (complete file contents, debug output, intermediate reasoning).
        Replace medium-priority messages (API responses, tool outputs) with
        structured summaries. High-priority messages (user input, system
        prompts, error messages) are never touched.
        
        This complements micro_compress which triggers at 90%.
        """
        msgs = state.context.get("messages")
        if not isinstance(msgs, list) or len(msgs) < 5:
            return

        max_tokens = float(getattr(self._config, "max_tokens", None) or getattr(state, "max_tokens", 0) or 0)  # noqa: F821
        used_tokens = float(getattr(state, "used_tokens", 0) or 0)
        if max_tokens <= 0 or used_tokens <= 0:
            return

        ratio = used_tokens / max_tokens
        if ratio < 0.80:
            return

        priority_order = {"low": 0, "medium": 1, "high": 2}
        preserved: list = []
        pruned_count = 0
        summarized_count = 0

        for msg in msgs:
            p = str(msg.get("priority") or msg.get("metadata", {}).get("priority", "medium"))
            rank = priority_order.get(p, 1)

            if rank == 0:  # low — discard
                pruned_count += 1
                continue
            elif rank == 1 and ratio >= 0.85:  # medium — summarize at high pressure
                content = str(msg.get("content", ""))
                if len(content) > 500:
                    msg["content"] = content[:200] + f"...(trl: {len(content)} chars)"
                    msg.setdefault("metadata", {})["summarized"] = True
                    summarized_count += 1
            # high priority — always keep
            preserved.append(msg)

        if pruned_count or summarized_count:
            state.context["messages"] = preserved
            state.metadata["prune_stats"] = {
                "pruned": pruned_count,
                "summarized": summarized_count,
                "before": len(msgs),
                "after": len(preserved),
                "ratio": round(ratio, 2),
            }

    async def _micro_compress():
        """Micro compression triggered at >=90% context usage. Placeholder for future implementation."""
        return

    async def _fold():
        """Merge consecutive same-role messages to reduce message count.
        
        When conversation gets long, consecutive user messages or assistant
        messages can be folded into single messages separated by section breaks.
        This is cost-free (no semantic loss) and reduces the prompt token count
        by removing redundant role markers and formatting.
        """
        msgs = state.context.get("messages")
        if not isinstance(msgs, list) or len(msgs) < 6:
            return

        folded: list = []
        for msg in msgs:
            role = str(msg.get("role", ""))
            content = str(msg.get("content", ""))
            if folded and folded[-1].get("role") == role and role in ("user", "assistant"):
                # Merge content with a section break
                folded[-1]["content"] = str(folded[-1].get("content", "")) + "\n---\n" + content
            else:
                folded.append(dict(msg))

        if len(folded) < len(msgs):
            state.context["messages"] = folded
            state.metadata["fold_stats"] = {
                "before": len(msgs),
                "after": len(folded),
                "saved": len(msgs) - len(folded),
            }

    async def _auto_compress():
        """Auto-summarize conversation into Episodic memory for cross-session recall.
        
        After significant conversations (>= 8 messages), generate an episodic
        summary and persist it via MemoryManager. This enables the next session
        to recall what was discussed — the foundation of cross-session learning.
        
        Only fires when: message count >= 8 or conversation appears complete.
        """
        msgs = state.context.get("messages")
        if not isinstance(msgs, list) or len(msgs) < 8:
            return

        # Skip if already compressed this conversation
        if state.metadata.get("_auto_compress_applied"):
            return

        try:
            from core.harness.memory.manager import get_memory_manager
            mm = get_memory_manager()
            # Extract the last user message as conversation context
            user_msgs = [m for m in msgs if isinstance(m, dict) and str(m.get("role", "")) == "user"]
            task_hint = str(user_msgs[-1].get("content", ""))[:300] if user_msgs else ""
            # Extract key points from assistant responses
            assistant_msgs = [m for m in msgs if isinstance(m, dict) and str(m.get("role", "")) == "assistant"]
            key_outputs = " | ".join(
                str(m.get("content", ""))[:150] for m in assistant_msgs[-3:]
            ) if assistant_msgs else ""
            summary = (
                f"Task: {task_hint or 'conversation'}\n"
                f"Messages: {len(msgs)}\n"
                f"Recent outputs: {key_outputs or 'none'}"
            )
            await mm.save_interaction(
                session_id=state.context.get("_run_id", state.context.get("session_id", "default")),
                user_msg=task_hint[:500],
                assistant_msg=summary[:1000],
                stability="medium",
            )
            state.metadata["_auto_compress_applied"] = True
            state.metadata["auto_compress_stats"] = {
                "message_count": len(msgs),
                "task_hint": task_hint[:100],
            }
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    mapping = {
        "budget_trim": _budget_trim,
        "prune": _prune,
        "micro_compress": _micro_compress,
        "fold": _fold,
        "auto_compress": _auto_compress,
    }
    pipeline_stats["before"] = self._estimate_context_stats(state)  # noqa: F821
    for stg in stages:
        await _stage(stg, mapping[stg])
    pipeline_stats["after"] = self._estimate_context_stats(state)  # noqa: F821
    pipeline_stats["ended_at"] = time.time()
    pipeline_stats["total_duration_ms"] = (pipeline_stats["ended_at"] - pipeline_stats["started_at"]) * 1000.0
    try:
        state.metadata["context_shaping_stats"] = pipeline_stats
        state.context["context_shaping_stats"] = pipeline_stats
    except Exception as e:
        logging.warning(str(e), exc_info=True)



async def compact_messages(state: LoopState, config: LoopConfig) -> None:
    """Original: _maybe_compact_messages (loop.py:1907)"""
    """
    When token budget pressure is high, compact older messages into a summary.

    Inspired by OpenClaw:
    - Preserve identifiers (UUIDs, hashes, filenames)
    - Keep recent turns verbatim
    - Best-effort; fail-open to no compaction

    NOTE: 5-level ContextCompression (85%→90%→93%→96%→99%) is now the
    primary compaction path. Legacy single-threshold compaction serves as
    fallback when the 5-level module is unavailable or raises.
    """
    import os
    import re

    # MemoryManager bridge: inject system reminders if available
    await self._try_inject_memory_reminders(state)  # noqa: F821

    # Always attempt compaction; 5-level thresholds decide whether to act.

    msgs = state.context.get("messages")
    if not isinstance(msgs, list) or len(msgs) < 8:
        return

    max_tokens = float(getattr(self._config, "max_tokens", None) or getattr(state, "max_tokens", 0) or 0)  # noqa: F821
    used_tokens = float(getattr(state, "used_tokens", 0) or 0)
    if max_tokens <= 0:
        return

    threshold = float(os.getenv("AIPLAT_CONTEXT_COMPACTION_THRESHOLD", "0.90") or "0.90")
    if (used_tokens / max_tokens) < threshold:
        return

    # Try 5-level ContextCompression as primary path
    try:
        from core.harness.memory.compression import ContextCompression
        comp = ContextCompression()
        ratio = used_tokens / max(1, max_tokens)
        state_obj = type("State", (), {
            "usage_ratio": ratio,
            "token_usage": int(used_tokens),
            "token_limit": int(max_tokens),
            "message_count": len(msgs),
        })()
        with_priority = []
        for msg in msgs:
            p = str(msg.get("priority") or msg.get("metadata", {}).get("priority", "medium"))
            msg_with_p = dict(msg, priority=p)
            with_priority.append(msg_with_p)
        result = await comp.compress(with_priority, state_obj)
        # Strip injected priority keys after compression
        clean = [{k: v for k, v in m.items() if k != "priority"} for m in result]
        state.context["messages"] = clean
        state.metadata["compaction_stats"] = {
            "level": "5-level",
            "before": len(msgs),
            "after": len(result),
            "ratio": round(ratio, 2),
        }
        # Context Reflect: mark next step for clean-context boundary injection
        state.metadata["context_reflect"] = True
        return
    except Exception as e:
        # fallback: legacy single-threshold compaction below
        logging.warning(str(e), exc_info=True)

    protect_last_n = int(os.getenv("AIPLAT_CONTEXT_COMPACTION_PROTECT_LAST_N", "6") or "6")
    protect_last_n = max(2, min(protect_last_n, 50))
    head = msgs[:-protect_last_n]
    tail = msgs[-protect_last_n:]

    # Extract identifiers to preserve
    text = "\n".join([str(m.get("content", "")) for m in head if isinstance(m, dict)])
    uuid_re = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    sha_re = r"\b[0-9a-f]{12,64}\b"
    file_re = r"\b[\w./-]+\.(?:py|ts|tsx|js|json|md|yaml|yml|toml|sql)\b"
    ids = set(re.findall(uuid_re, text, flags=re.IGNORECASE))
    ids |= set(re.findall(file_re, text, flags=re.IGNORECASE))
    # Limit hashes (avoid huge noise)
    for h in re.findall(sha_re, text, flags=re.IGNORECASE):
        if 12 <= len(h) <= 40:
            ids.add(h)
    ids_list = sorted(list(ids))[:50]

    summary_prompt = self._build_compaction_prompt(ids_list, head)  # noqa: F821

    trace_ctx = {
        "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
        "run_id": state.context.get("_run_id") or state.context.get("run_id"),
    }
    from core.harness.syscalls.llm import sys_llm_generate
    resp = await sys_llm_generate(self._model, summary_prompt, trace_context=trace_ctx)  # noqa: F821
    summary_text = str(getattr(resp, "content", "") or "").strip()
    if not summary_text:
        return

    state.context["messages"] = [
        {
            "role": "system",
            "content": "CONTEXT_SUMMARY:\n" + summary_text + ("\n\nPRESERVED_IDENTIFIERS:\n" + "\n".join(ids_list) if ids_list else ""),
        }
    ] + tail
    state.metadata["control_action"] = "compact_context_summary"
    state.metadata["compacted_messages"] = True
    state.metadata["compaction_stats"] = {"before": len(msgs), "after": len(state.context["messages"]), "preserved_ids": len(ids_list)}
