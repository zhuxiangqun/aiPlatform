"""
ReAct Inference Engine — extracted from loop.py._reason().

Pure logic: receives explicit parameters, returns reasoning text.
Zero dependency on ReActLoop instance state.
"""

from typing import Any, Dict, List, Optional, Tuple
import json, os, time, re, logging

from ...interfaces.loop import LoopState, LoopConfig
from ...syscalls import sys_llm_generate
from ...assembly import PromptAssembler, ContextAssembler, ContextSource
from ...kernel.runtime import get_kernel_runtime
from ...infrastructure.hooks import HookPhase
from ..tool_calling import parse_action_call


async def reason(
    state: LoopState,
    model: Any,
    config: LoopConfig,
    skills: List[Any],
    tools: List[Any],
    hook_manager: Any = None,
    model_client: Any = None,
) -> str:
    """Execute a single LLM reasoning call."""
    # ── original: async def _reason(self, state: LoopState) -> str:
    """Reasoning phase"""
    if not self._model:  # noqa: F821
        return "No model available"

    # Preflight: estimate token pressure before sending request.
    # Avoids "send → rejected → compress → resend" waste loop.
    msgs = state.context.get("messages")
    if isinstance(msgs, list) and len(msgs) > 6:
        estimated_tokens = state.used_tokens or sum(
            len(str(m.get("content", ""))).split() * 1.3 for m in msgs if isinstance(m, dict)
        )
        max_tokens = float(getattr(self._config, "max_tokens", 0) or 0)  # noqa: F821
        if max_tokens > 0 and estimated_tokens / max_tokens > 0.80:
            await self._maybe_compact_messages(state)  # noqa: F821

    # Optional: context compaction + memory injection (best-effort)
    try:
        await self._maybe_compact_messages(state)  # noqa: F821
        from ...memory.manager import get_memory_manager
        try:
            mgr = get_memory_manager()
            task = state.context.get("task", "")
            sys_prompt = state.context.get("system_prompt", "")
            mem_ctx = await mgr.build_context(current_query=task, system_prompt=sys_prompt)
            if mem_ctx and (mem_ctx.working_context or mem_ctx.messages):
                state.context.setdefault("_memory_context", {
                    "working": str(mem_ctx.working_context)[:2000] if mem_ctx.working_context else "",
                    "episodic": str(mem_ctx.episodic_summary)[:1000] if mem_ctx.episodic_summary else "",
                    "semantic": str(mem_ctx.relevant_memories)[:1000] if mem_ctx.relevant_memories else "",
                    "messages": mem_ctx.messages,
                    "token_count": mem_ctx.token_count,
                })
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Drain AgentMessageBus before reasoning (P1: wire feedback/coordination messages)
    try:
        from ...interfaces.messaging import get_message_bus
        bus = get_message_bus()
        agent_id = state.context.get("agent_id", "") or getattr(self._config, 'name', 'react_agent')  # noqa: F821
        messages = bus.drain(agent_id)
        if messages:
            state.context.setdefault("_bus_messages", []).extend(str(m)[:200] for m in messages)
        # Check for pending requests that need responses
        requests = bus.collect_requests(agent_id)
        if requests:
            state.context.setdefault("_bus_requests", []).extend(
                {"request_id": r.msg_id, "sender": r.sender_id, "payload": r.payload}
                for r in requests[:3])
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Query rewrite: resolve pronouns and implicit references via conversational RAG (§03)
    try:
        enable_qr = state.context.get("_enable_query_rewrite") or os.getenv("AIPLAT_ENABLE_QUERY_REWRITE", "").lower() in ("1", "true", "yes")
        if enable_qr:
            current_query = state.context.get("task", "")
            history = state.context.get("messages", [])
            from core.harness.knowledge.query_rewriter import rewrite_with_history
            rewritten = await rewrite_with_history(current_query, history, self._model)  # noqa: F821
            if rewritten and rewritten != current_query:
                state.context["_original_query"] = current_query
                state.context["task"] = rewritten
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Inject code graph context on first reasoning call (replaces grep/glob exploration)
    graph_hints = await self._try_inject_graph_context(state)  # noqa: F821
    if graph_hints:
        state.context.setdefault("_graph_hints", graph_hints)

    # Inject memory context + bus messages into prompt assembly
    mem_hints = ""
    try:
        mem = state.context.get("_memory_context")
        if mem:
            parts = []
            if mem.get("working"): parts.append(f"Working Memory: {mem['working']}")
            if mem.get("episodic"): parts.append(f"Recent: {mem['episodic']}")
            if mem.get("semantic"): parts.append(f"Relevant: {mem['semantic']}")
            mem_hints = "\n".join(parts)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    bus_hints = ""
    try:
        bus_msgs = state.context.get("_bus_messages", [])
        if bus_msgs:
            bus_hints = "\n".join(f"[Bus] {m}" for m in bus_msgs[-3:])
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    task = state.context.get("task", "")
    history = "\n".join([
        f"{msg.get('role', 'user')}: {msg.get('content', '')}"
        for msg in state.context.get("messages", [])[-5:]
    ])
    tools_desc, tools_desc_stats = self._build_tools_desc()  # noqa: F821
    # 上下文压力（best-effort）：用于渐进式披露预算
    try:
        max_tokens = float(getattr(self._config, "max_tokens", state.max_tokens) or state.max_tokens)  # noqa: F821
        used_tokens = float(getattr(state, "used_tokens", 0) or 0)
        pressure = (used_tokens / max_tokens) if max_tokens > 0 else 0.0
    except Exception:
        pressure = 0.0
    skills_desc, skills_desc_stats = self._build_skills_desc(context_pressure=pressure)  # noqa: F821
    # Best-effort: attach to state for observability/debugging
    try:
        state.metadata["tools_desc_stats"] = tools_desc_stats
        state.context["tools_desc_stats"] = tools_desc_stats
        state.metadata["skills_desc_stats"] = skills_desc_stats
        state.context["skills_desc_stats"] = skills_desc_stats
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # ── ContextAssembler: token budget + source attribution (Phase 9) ──
    try:
        from ...assembly import BudgetSpec
        sources = [
            ContextSource(key="tools_desc", origin="system", token_estimate=len(tools_desc) // 4, priority="high"),
            ContextSource(key="skills_desc", origin="skill", token_estimate=len(skills_desc) // 4, priority="medium"),
            ContextSource(key="history", origin="system", token_estimate=len(history) // 4, priority="medium"),
        ]
        tool_schemas = [{"name": getattr(t, "name", str(t)), "desc": str(getattr(getattr(t, '_config', None), 'description', ''))[:200]} for t in (self._tools or [])]  # noqa: F821
        skill_schemas = [{"name": getattr(s, "name", str(s)), "desc": str(getattr(getattr(s, '_config', None), 'description', ''))[:200]} for s in (self._skills or [])]  # noqa: F821
        assembly_result = ContextAssembler().assemble(
            messages=state.context.get("messages", []),
            session_id=state.context.get("session_id"),
            user_id=state.context.get("user_id"),
            budgets=BudgetSpec(token_budget=self._config.max_tokens or 100_000),  # noqa: F821
            sources=sources,
            tool_schemas=tool_schemas,
            skill_schemas=skill_schemas,
            metadata={"step_count": int(getattr(state, "step_count", 0) or 0)},
        )
        state.context["_context_assembly"] = {
            "estimated_tokens": assembly_result.context.estimated_tokens(),
            "over_budget": assembly_result.context.is_over_budget(),
            "compact_needed": assembly_result.context.compact_needed(),
            "prompt_version": assembly_result.context.prompt_version,
            "meta": assembly_result.metadata,
        }
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # P1-2: persist disclosure policy/budgets for replay (best-effort, de-duplicated)
    try:
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        run_id0 = state.context.get("_run_id") or state.context.get("run_id")
        if store is not None and run_id0 and hasattr(store, "append_run_event"):
            # Emit only when policy/budget changes to reduce noise.
            key_fields = {
                "disclosure_policy": skills_desc_stats.get("disclosure_policy"),
                "per_skill_max_chars": skills_desc_stats.get("per_skill_max_chars"),
                "total_max_chars": skills_desc_stats.get("total_max_chars"),
                "skill_sop_recommended_max_chars": skills_desc_stats.get("skill_sop_recommended_max_chars"),
            }
            last = state.metadata.get("_skills_disclosure_last")
            if last != key_fields:
                state.metadata["_skills_disclosure_last"] = dict(key_fields)
                await store.append_run_event(
                    run_id=str(run_id0),
                    event_type="skills_disclosure",
                    trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                    tenant_id=state.context.get("tenant_id"),
                    payload={
                        "step_count": int(getattr(state, "step_count", 0) or 0),
                        "context_pressure": float(pressure),
                        "used_tokens": float(getattr(state, "used_tokens", 0) or 0),
                        "max_tokens": float(getattr(self._config, "max_tokens", state.max_tokens) or state.max_tokens),  # noqa: F821
                        "budgets": key_fields,
                    },
                )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # P0: context shaping pipeline (observable, default enabled)
    try:
        await self._apply_context_shaping_pipeline(state)  # noqa: F821
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Restatement: load latest run_state and periodically refresh next_step
    try:
        await self._load_run_state_for_prompt(state)  # noqa: F821
        await self._maybe_restate_and_persist_run_state(state)  # noqa: F821
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true").lower() in ("1", "true", "yes", "y"):
        prompt = PromptAssembler().build_react_reasoning_messages(
            task=task,
            history=history,
            tools_desc=tools_desc,
            skills_desc=skills_desc,
            observation=state.context.get("observation", "None"),
        )
        # Inject system_prompt as a system message if configured
        sp = state.context.get("_sys_prompt", "") or state.context.get("system_prompt", "")
        if sp:
            # Remove any existing system message and prepend with sys_prompt
            prompt = [m for m in prompt if m.get("role") != "system"]
            prompt.insert(0, {"role": "system", "content": sp})
        rs = state.context.get("run_state")
        if isinstance(rs, dict):
            from core.harness.restatement.run_state import format_run_state_for_prompt
            prompt.append({"role": "user", "content": format_run_state_for_prompt(rs)})
        # Inject toolset behavioral constraints (force_tool_use, prefer_skill, prefer_agent_delegate)
        try:
            from core.harness.kernel.execution_context import get_active_workspace_context
            from core.harness.tools.toolsets import resolve_toolset
            ws = get_active_workspace_context()
            active_t = getattr(ws, 'toolset', None) if ws else None
            if active_t:
                policy = resolve_toolset(str(active_t))
                constraints = []
                if policy.force_tool_use:
                    if not state.context.get("_capability_attempted"):
                        constraints.append("You have not yet used any tool/skill/agent. You MUST call an available tool first. Do NOT answer from your own knowledge.")
                    else:
                        constraints.append("You may now respond with DONE to summarize results.")
                if policy.prefer_skill_use:
                    constraints.append("Prefer using your bound skills over raw tool calls when available.")
                if constraints:
                    toolset_instruction = "## Toolset Requirements\n" + "\n".join(f"- {c}" for c in constraints)
                    existing_sys = prompt[0].get("content", "") if prompt and prompt[0].get("role") == "system" else ""
                    if prompt and prompt[0].get("role") == "system":
                        prompt[0]["content"] = existing_sys + "\n\n" + toolset_instruction
                    else:
                        prompt.insert(0, {"role": "system", "content": toolset_instruction})
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    else:
        from core.harness.utils.prompt_loader import _sync_resolve
        prompt = _sync_resolve("react-reasoning",
            task=task, history=history, mem_hints=mem_hints, bus_hints=bus_hints,
            tools_desc=tools_desc, skills_desc=skills_desc,
            observation=str(state.context.get('observation', 'None')),
        )
        rs = state.context.get("run_state")
        if isinstance(rs, dict):
            prompt += "\n\n" + format_run_state_for_prompt(rs)
    try:
        trace_ctx = {
            "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
            "run_id": state.context.get("_run_id") or state.context.get("run_id"),
            "parent_span_id": state.context.get("_current_step_span_id") or (state.context.get("_agent_id") and f"agent:{state.context['_agent_id']}:start"),
            "knowledge_bases": state.context.get("_knowledge_bases", []),
        }
        response = await sys_llm_generate(self._model, prompt,  # noqa: F821
            trace_context=trace_ctx,
            model_name=self._config.model_name)  # noqa: F821
        # P1-2: 调用后跟踪 token usage，供下次调用前预估+预压缩
        # Persist this interaction to MemoryManager for cross-turn memory
        await self._try_save_interaction(state, prompt, getattr(response, "content", str(response)))  # noqa: F821
        # L3: Auto-extract user facts from conversation
        await self._try_extract_user_facts(state, prompt)  # noqa: F821
        # Track token usage (best-effort) for compaction budgets.
        try:
            usage = getattr(response, "usage", None)
            if isinstance(usage, dict):
                total = usage.get("total_tokens")
                if total is None:
                    total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
                state.used_tokens = float(getattr(state, "used_tokens", 0) or 0) + float(total or 0)
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        # Update budget_remaining
        _max = float(getattr(self._config, "max_tokens", 0) or 0)  # noqa: F821
        if _max > 0:
            state.budget_remaining = max(0.0, 1.0 - (state.used_tokens / _max))
        return response.content
    except Exception as e:
        # P3-15: Session overflow fallback — retry with emergency compression
        err_msg = str(e).lower()
        overflow_keywords = [
            "context_length", "too long", "reduce the length",
            "token limit", "max tokens", "context window",
            "too many tokens", "truncat",
        ]
        if any(kw in err_msg for kw in overflow_keywords) and not state.context.get("_overflow_retried"):
            state.context["_overflow_retried"] = True
            state.context["_last_action_reason"] = "context_overflow_compressing"
            try:
                from core.harness.memory.compression import ContextCompression, ContextState
                comp = ContextCompression()
                msgs = state.context.get("messages", [])
                est_tokens = len(json.dumps(msgs, default=str)) // 4 if msgs else 0
                cs = ContextState(token_usage=est_tokens, token_limit=est_tokens * 2, message_count=len(msgs))
                compressed = await comp._emergency_compress(msgs) if msgs else []
                if compressed:
                    # Rebuild a minimal prompt from compressed messages
                    system_text = "\n".join(
                        m.get("content", "")[:500] for m in compressed
                        if m.get("role") == "system"
                    )
                    last_text = "\n".join(
                        m.get("content", "")[:300] for m in compressed
                        if m.get("role") != "system"
                    )
                    emergency_prompt = f"{system_text}\n\n## Context (compressed)\n{last_text}\n\n## Current Task\n{state.context.get('task', '')}\n\nRespond with DONE: ..."
                    response = await sys_llm_generate(self._model, emergency_prompt,  # noqa: F821
                        trace_context=trace_ctx, model_name=self._config.model_name)  # noqa: F821
                    return response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        # Track consecutive LLM failures for observability
        cf = state.context.get("_consecutive_llm_failures", 0) + 1
        state.context["_consecutive_llm_failures"] = cf
        state.context["_last_action_reason"] = f"llm_call_failed:#{cf}"
        max_cf = state.context.get("_max_consecutive_llm_failures", int(os.getenv("AIPLAT_MAX_CONSECUTIVE_LLM_FAILURES", "3") or "3"))
        if cf >= max_cf:
            state.context["_stop_reason"] = "llm_failure_exhausted"
        return f"Model error: {e}"
