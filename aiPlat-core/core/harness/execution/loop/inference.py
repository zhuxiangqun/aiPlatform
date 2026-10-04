"""
ReAct Inference Engine — extracted from loop.py._reason().

Pure logic: receives explicit parameters, returns reasoning text.
Zero dependency on ReActLoop instance state.
"""

from typing import Any, Dict, List, Optional, Tuple
import json, os, time, re, logging
import logging

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
    loop: Any = None,
) -> str:
    """Execute a single LLM reasoning call."""
    # ── original: async def _reason(self, state: LoopState) -> str:
    """Reasoning phase"""
    if not model:
        return "No model available"

    # Preflight: estimate token pressure before sending request.
    # Avoids "send → rejected → compress → resend" waste loop.
    msgs = state.context.get("messages")
    if isinstance(msgs, list) and len(msgs) > 6:
        estimated_tokens = state.used_tokens or sum(
            len(str(m.get("content", "")).split()) * 1.3 for m in msgs if isinstance(m, dict)
        )
        max_tokens = float(getattr(config, "max_tokens", 0) or 0)
        if max_tokens > 0 and estimated_tokens / max_tokens > 0.80:
            await loop._maybe_compact_messages(state)

    # Optional: context compaction + memory injection (best-effort)
    # Hang fix: coding_policy=off (workspace oral agents) must NOT pay for
    # semantic retrieve → SentenceTransformer cold-start on the event loop.
    # That path left only step_1/context_snapshot with zero llm syscalls.
    try:
        await loop._maybe_compact_messages(state)
        from ...memory.manager import get_memory_manager
        import asyncio as _aio_mem
        try:
            mgr = get_memory_manager()
            # Phase 49: set domain context for Decision Lineage version tracking
            domain_id = state.context.get("domain_id", "") or state.context.get("domain", {}).get("id", "")
            if domain_id:
                try:
                    mgr.set_domain_context(domain_id, state.context.get("collection_id", ""))
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            task = state.context.get("task", "")
            sys_prompt = state.context.get("system_prompt", "")
            _prof = str(
                state.context.get("_coding_policy_profile")
                or state.context.get("coding_policy_profile")
                or ""
            ).strip().lower()
            _budget = (
                "working_only"
                if _prof in ("off", "none", "0", "false", "minimal")
                else "full"
            )
            try:
                _mem_timeout = float(os.getenv("AIPLAT_MEMORY_BUILD_TIMEOUT", "8") or "8")
            except Exception:
                _mem_timeout = 8.0
            mem_ctx = await _aio_mem.wait_for(
                mgr.build_context(
                    current_query=task,
                    system_prompt=sys_prompt,
                    retrieval_budget=_budget,
                ),
                timeout=max(1.0, _mem_timeout),
            )
            if mem_ctx and (mem_ctx.working_context or mem_ctx.messages):
                state.context.setdefault("_memory_context", {
                    "working": str(mem_ctx.working_context)[:2000] if mem_ctx.working_context else "",
                    "episodic": str(mem_ctx.episodic_summary)[:1000] if mem_ctx.episodic_summary else "",
                    "semantic": str(mem_ctx.relevant_memories)[:1000] if mem_ctx.relevant_memories else "",
                    "messages": mem_ctx.messages,
                    "token_count": mem_ctx.token_count,
                })
        except _aio_mem.TimeoutError:
            logging.getLogger(__name__).warning(
                "memory build_context timed out — continuing to LLM without memory inject"
            )
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # ── Knowledge Retrieval: inject domain knowledge into agent context ──
    try:
        _task = state.context.get("task", "")
        _domain = state.context.get("domain_id", "") or state.get("domain_id", "")
        if _task and _domain:
            from core.harness.syscalls.retrieval import sys_knowledge_retrieve
            _kb = sys_knowledge_retrieve(_task, top_k=3, domain_id=_domain)
            if _kb:
                _kb_text = "## Existing relevant knowledge base content\n" + "\n".join(
                    f"- {getattr(d, 'title', '') or ''}: {str(getattr(d, 'content', '') or getattr(d, 'snippet', ''))[:300]}"
                    for d in _kb[:3] if getattr(d, 'title', None) or getattr(d, 'content', None)
                )
                state.context["_knowledge_context"] = _kb_text
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    # Drain AgentMessageBus before reasoning (P1: wire feedback/coordination messages)
    try:
        from ...interfaces.messaging import get_message_bus
        bus = get_message_bus()
        agent_id = state.context.get("agent_id", "") or getattr(config, 'name', 'react_agent')
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

    # Query rewrite: only when multi-turn history exists (avoids phantom LLM
    # before first generate on oral workspace agents).
    try:
        enable_qr = state.context.get("_enable_query_rewrite") or os.getenv("AIPLAT_ENABLE_QUERY_REWRITE", "").lower() in ("1", "true", "yes")
        history = state.context.get("messages", [])
        if enable_qr and isinstance(history, list) and len(history) >= 2:
            current_query = state.context.get("task", "")
            from core.harness.knowledge.query_rewriter import rewrite_with_history
            import asyncio as _aio_qr
            try:
                rewritten = await _aio_qr.wait_for(
                    rewrite_with_history(current_query, history, model),
                    timeout=float(os.getenv("AIPLAT_QUERY_REWRITE_TIMEOUT", "15") or "15"),
                )
            except _aio_qr.TimeoutError:
                logging.getLogger(__name__).warning(
                    "query rewrite timed out — continuing with original task"
                )
                rewritten = None
            if rewritten and rewritten != current_query:
                state.context["_original_query"] = current_query
                state.context["task"] = rewritten
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # v2.8: Slash command routing — "/assess finance" → skill invocation
    task = state.context.get("task", "")
    if task.startswith("/"):
        try:
            from core.harness.execution.loop.command_parser import parse as _parse_cmd
            from core.harness.execution.loop.command_parser import get_agent_commands, resolve_skill
            cmd = _parse_cmd(task)
            if cmd:
                # PR #4: /profile command — session-level profile override
                if cmd.name == "profile":
                    profile_name = cmd.args[0] if cmd.args else "default"
                    try:
                        from core.harness.meta.profile_registry import (
                            set_profile_override, ProfileRegistry, get_active_profile,
                        )
                        reg = ProfileRegistry.instance()
                        if reg.get_preset(profile_name):
                            set_profile_override(profile_name)
                            return f"[Profile] Switched to '{profile_name}' — {reg.get_preset(profile_name).model_tier}"
                        else:
                            available = reg.list_presets()
                            return f"[Profile] Unknown '{profile_name}'. Available: {', '.join(available)}"
                    except Exception as e:
                        return f"[Profile] Error: {e}"

                if cmd.name == "profile_status":
                    try:
                        from core.harness.meta.profile_registry import (
                            get_active_profile, list_profile_overrides,
                        )
                        profile = get_active_profile()
                        lines = [
                            f"**Active Profile**",
                            f"- model_tier: {profile.model_tier}",
                            f"- temperature: {profile.temperature}",
                            f"- orchestration: {profile.orchestration_mode}",
                            f"- compression_strictness: {profile.compression_strictness}",
                            f"- gate_strictness: {profile.gate_strictness}",
                            f"- episodic_injection: {profile.episodic_injection}",
                        ]
                        overrides = list_profile_overrides()
                        if overrides:
                            lines.append(f"- session_override: {overrides.get('_global', 'none')}")
                        return "\n".join(lines)
                    except Exception as e:
                        return f"[Profile] Error: {e}"

                agent_id = state.context.get("_agent_id", "") or "fde_solution_architect"
                agent_cmds = get_agent_commands(agent_id)
                resolved = resolve_skill(cmd, agent_cmds)
                if resolved and resolved.skill_name:
                    from core.harness.syscalls.skill import sys_skill_call
                    result = await sys_skill_call(
                        resolved.skill_name,
                        params={"context": " ".join(cmd.args)},
                        trace_context={"agent_id": agent_id, "command": cmd.name},
                    )
                    return str(result)
        except Exception as e:
            logging.debug("Command parsing skipped: %s", e)

    # Inject code graph context on first reasoning call (replaces grep/glob exploration)
    # Hard budget for ALL pre-LLM prep so step_1 cannot wedge the event loop forever
    # (UI then shows only 「准备 · LLM 前置」with 0 llm spans).
    import asyncio as _aio_prep

    try:
        _prep_budget = float(os.getenv("AIPLAT_PRE_LLM_PREP_TIMEOUT", "45") or "45")
    except Exception:
        _prep_budget = 45.0
    _prep_budget = max(5.0, _prep_budget)

    async def _assemble_prompt_ready() -> Any:
        graph_hints = await loop._try_inject_graph_context(state)
        if graph_hints:
            state.context.setdefault("_graph_hints", graph_hints)

        # Inject ontology domain context (v2.6 — DomainRouter classify + class list)
        await loop._try_inject_ontology_context(state)

        # Inject memory context + bus messages into prompt assembly
        mem_hints_local = ""
        try:
            mem = state.context.get("_memory_context")
            if mem:
                parts = []
                if mem.get("working"):
                    parts.append(f"Working Memory: {mem['working']}")
                if mem.get("episodic"):
                    parts.append(f"Recent: {mem['episodic']}")
                if mem.get("semantic"):
                    parts.append(f"Relevant: {mem['semantic']}")
                mem_hints_local = "\n".join(parts)
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        bus_hints_local = ""
        try:
            bus_msgs = state.context.get("_bus_messages", [])
            if bus_msgs:
                bus_hints_local = "\n".join(f"[Bus] {m}" for m in bus_msgs[-3:])
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        task_local = state.context.get("task", "")
        history_local = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in state.context.get("messages", [])[-5:]
        ])
        # Sync skill/tool index builds can block the event loop on large workspaces.
        try:
            tools_desc_local, tools_desc_stats = await _aio_prep.wait_for(
                _aio_prep.to_thread(loop._build_tools_desc),
                timeout=min(8.0, _prep_budget),
            )
        except Exception:
            tools_desc_local, tools_desc_stats = "", {}
        try:
            max_tokens = float(getattr(config, "max_tokens", state.max_tokens) or state.max_tokens)
            used_tokens = float(getattr(state, "used_tokens", 0) or 0)
            pressure = (used_tokens / max_tokens) if max_tokens > 0 else 0.0
        except Exception:
            pressure = 0.0
        try:
            skills_desc_local, skills_desc_stats = await _aio_prep.wait_for(
                _aio_prep.to_thread(loop._build_skills_desc, context_pressure=pressure),
                timeout=min(8.0, _prep_budget),
            )
        except Exception:
            skills_desc_local, skills_desc_stats = "", {}
        try:
            state.metadata["tools_desc_stats"] = tools_desc_stats
            state.context["tools_desc_stats"] = tools_desc_stats
            state.metadata["skills_desc_stats"] = skills_desc_stats
            state.context["skills_desc_stats"] = skills_desc_stats
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        # Keep downstream assembly using the same locals via state
        state.context["_prep_tools_desc"] = tools_desc_local
        state.context["_prep_skills_desc"] = skills_desc_local
        state.context["_prep_mem_hints"] = mem_hints_local
        state.context["_prep_bus_hints"] = bus_hints_local
        state.context["_prep_history"] = history_local
        state.context["_prep_task"] = task_local
        return True

    try:
        await _aio_prep.wait_for(_assemble_prompt_ready(), timeout=_prep_budget)
    except _aio_prep.TimeoutError:
        logging.getLogger(__name__).warning(
            "pre-LLM prep timed out after %.0fs — continuing with minimal prompt",
            _prep_budget,
        )
        state.context.setdefault("_prep_tools_desc", "")
        state.context.setdefault("_prep_skills_desc", "")
        state.context.setdefault("_prep_mem_hints", "")
        state.context.setdefault("_prep_bus_hints", "")
        state.context.setdefault(
            "_prep_history",
            "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                for msg in state.context.get("messages", [])[-5:]
            ]),
        )
        state.context.setdefault("_prep_task", state.context.get("task", ""))
        # Close prep marker as timeout so UI leaves 「执行中」
        try:
            _rid = str(state.context.get("_run_id") or "")
            if _rid:
                from core.harness.utils.execute_session import emit_pre_llm_prep_close
                from core.services.execution_store import get_execution_store as _ges_prep_to

                await emit_pre_llm_prep_close(
                    _ges_prep_to(),
                    _rid,
                    status="timeout",
                    step_count=state.step_count,
                    parent_span_id=str(state.context.get("_current_step_span_id") or ""),
                    reason="prep_timeout",
                    extra_args={"budget_s": _prep_budget},
                    error="pre_llm_prep_timeout",
                )
        except Exception:
            logging.debug("pre_llm_prep timeout close failed", exc_info=True)

    tools_desc = str(state.context.get("_prep_tools_desc") or "")
    skills_desc = str(state.context.get("_prep_skills_desc") or "")
    mem_hints = str(state.context.get("_prep_mem_hints") or "")
    bus_hints = str(state.context.get("_prep_bus_hints") or "")
    task = str(state.context.get("_prep_task") or state.context.get("task") or "")
    history = str(state.context.get("_prep_history") or "")
    tools_desc_stats = state.context.get("tools_desc_stats") if isinstance(state.context.get("tools_desc_stats"), dict) else {}
    skills_desc_stats = state.context.get("skills_desc_stats") if isinstance(state.context.get("skills_desc_stats"), dict) else {}
    try:
        max_tokens = float(getattr(config, "max_tokens", state.max_tokens) or state.max_tokens)
        used_tokens = float(getattr(state, "used_tokens", 0) or 0)
        pressure = (used_tokens / max_tokens) if max_tokens > 0 else 0.0
    except Exception:
        pressure = 0.0

    # ── ContextAssembler: token budget + source attribution (Phase 9) ──
    try:
        from ...assembly import BudgetSpec
        sources = [
            ContextSource(key="tools_desc", origin="system", token_estimate=len(tools_desc) // 4, priority="high"),
            ContextSource(key="skills_desc", origin="skill", token_estimate=len(skills_desc) // 4, priority="medium"),
            ContextSource(key="history", origin="system", token_estimate=len(history) // 4, priority="medium"),
        ]
        tool_schemas = [{"name": getattr(t, "name", str(t)), "desc": str(getattr(getattr(t, '_config', None), 'description', ''))[:200]} for t in (tools or [])]
        skill_schemas = [{"name": getattr(s, "name", str(s)), "desc": str(getattr(getattr(s, '_config', None), 'description', ''))[:200]} for s in (skills or [])]
        assembly_result = ContextAssembler().assemble(
            messages=state.context.get("messages", []),
            session_id=state.context.get("session_id"),
            user_id=state.context.get("user_id"),
            budgets=BudgetSpec(token_budget=config.max_tokens or 100_000),
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
                        "max_tokens": float(getattr(config, "max_tokens", state.max_tokens) or state.max_tokens),
                        "budgets": key_fields,
                    },
                )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # P0: context shaping pipeline (observable, default enabled)
    try:
        await _aio_prep.wait_for(
            loop._apply_context_shaping_pipeline(state),
            timeout=min(10.0, max(3.0, _prep_budget * 0.25)),
        )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Restatement: load latest run_state and periodically refresh next_step
    try:
        await _aio_prep.wait_for(
            loop._load_run_state_for_prompt(state),
            timeout=3.0,
        )
        await _aio_prep.wait_for(
            loop._maybe_restate_and_persist_run_state(state),
            timeout=3.0,
        )
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
        # After primary skill delivery (skill_delivery=once):
        # if a bound review skill is still pending, steer there; else force DONE.
        try:
            delivered = str(state.context.get("_primary_skill_delivered") or "").strip()
            if delivered and str(state.context.get("_skill_delivery") or "").lower() == "once":
                follow = None
                try:
                    if loop is not None and hasattr(loop, "_pending_coding_followup"):
                        follow = loop._pending_coding_followup(state)
                except Exception:
                    follow = None
                if follow:
                    done_rule = (
                        f"## Delivery follow-up\n"
                        f"- Skill `{delivered}` already returned usable output (see Observation).\n"
                        f"- Do NOT re-call `{delivered}`.\n"
                        f"- Next you MUST call skill `{follow}` "
                        f"(type=skill_call) on the generated files, then DONE.\n"
                    )
                else:
                    done_rule = (
                        f"## Delivery complete\n"
                        f"- Skill `{delivered}` already returned usable output (see Observation).\n"
                        f"- Your reply MUST be {{\"type\":\"done\",\"answer\":...}} or DONE: …\n"
                        f"- Do NOT call `{delivered}` again unless Observation is an explicit error."
                    )
                if prompt and prompt[0].get("role") == "system":
                    prompt[0]["content"] = str(prompt[0].get("content") or "") + "\n\n" + done_rule
                else:
                    prompt.insert(0, {"role": "system", "content": done_rule})
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
            "step_count": int(state.step_count or 0),
            "knowledge_bases": state.context.get("_knowledge_bases", []),
            "coding_policy_profile": str(
                state.context.get("_coding_policy_profile")
                or state.context.get("coding_policy_profile")
                or ""
            ),
        }
        # Explicit opt-in only (AGENT.md / caller); never inferred for "doc agents".
        if state.context.get("_skip_claude_md"):
            trace_ctx["skip_claude_md"] = True
        # Close prep marker BEFORE generate so UI does not keep 「LLM 前置 · 执行中」
        # for the entire Ollama wait (which can be minutes).
        try:
            _rid = str(state.context.get("_run_id") or "")
            if _rid:
                from core.harness.utils.execute_session import emit_pre_llm_prep_close
                from core.services.execution_store import get_execution_store as _ges_prep

                await emit_pre_llm_prep_close(
                    _ges_prep(),
                    _rid,
                    status="ok",
                    step_count=state.step_count,
                    parent_span_id=str(state.context.get("_current_step_span_id") or ""),
                    reason="before_generate",
                )
        except Exception:
            logging.debug("pre_llm_prep close-before-generate failed", exc_info=True)
        response = await sys_llm_generate(model, prompt,
            trace_context=trace_ctx,
            model_name=config.model_name)
        # P1-2: track token usage after the call for pre-estimation + pre-compaction before the next call
        # Persist / fact-extract must never wedge ReAct before routing (run-1a2dd /
        # qa_agent run-44724b8b8107: generate=success then post_llm_zombie).
        # Fire-and-forget: even wait_for cannot interrupt a sync ModelManager /
        # SentenceTransformer load on the event loop.
        import asyncio as _aio_post
        if loop is not None:
            try:
                _aio_post.ensure_future(
                    loop._try_save_interaction(
                        state, prompt, getattr(response, "content", str(response))
                    )
                )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            try:
                _aio_post.ensure_future(loop._try_extract_user_facts(state, prompt))
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
        _max = float(getattr(config, "max_tokens", 0) or 0)
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
                    from core.harness.utils.prompt_loader import _sync_resolve
                    emergency_prompt = _sync_resolve("emergency-compression",
                        system_text=system_text, last_text=last_text,
                        task=state.context.get('task', ''))
                    response = await sys_llm_generate(model, emergency_prompt,
                        trace_context=trace_ctx, model_name=config.model_name)
                    return response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        # Track consecutive LLM failures for observability
        cf = state.context.get("_consecutive_llm_failures", 0) + 1
        state.context["_consecutive_llm_failures"] = cf
        state.context["_last_action_reason"] = f"llm_call_failed:#{cf}"
        # Prevent "Model error: …" from being treated as a plain-text final answer
        # (auto_done → false green / stuck running after llm_timeout).
        state.context["_llm_call_failed"] = True
        max_cf = state.context.get("_max_consecutive_llm_failures", int(os.getenv("AIPLAT_MAX_CONSECUTIVE_LLM_FAILURES", "3") or "3"))
        if cf >= max_cf:
            state.context["_stop_reason"] = "llm_failure_exhausted"
        return f"Model error: {e}"
