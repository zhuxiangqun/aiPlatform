"""
StageRunner — adapts a PipelineStageConfig into a ReActLoop run.

Phase A: Each generic pipeline stage delegates to ReActLoop.run() instead of
the engine's own _call_llm / _parse_output path.  Code-gen and test-runner
stages are not yet migrated (they use non-prompt-based execution).

Design principle (CLAUDE.md §5.22):
  LangGraph = transparency layer (node graph, checkpointing, visualization)
  Harness   = execution layer (ReActLoop, syscalls, hooks, token management)

This module is the bridge between the Builder pipeline config and the generic
Harness execution engine.
"""

from __future__ import annotations
import asyncio
import logging

from typing import Any, Dict, List, Optional

from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum
from core.schemas_builder import PipelineStageConfig


class StageRunner:
    def __init__(self, model=None, tools=None, skills=None, stage=None, pipeline_config=None):
        self._model = model
        self._tools = tools or []
        self._skills = skills or []
        self._stage = stage
        self._config = pipeline_config

    def _resolve_skills(self, stage=None) -> List[Any]:
        s = stage if stage is not None else self._stage
        if not s:
            return self._load_global_skills(self._skills or [])
        required = getattr(s, 'required_skills', None) or []
        if not required:
            return self._skills or []
        return self._load_global_skills(self._skills or [], filter_names=required)

    def _resolve_tools(self, override: Optional[List[str]] = None) -> List[Any]:
        if override is not None:
            return self._load_global_tools(override)
        if not self._stage:
            return self._load_global_tools(self._tools)
        if self._tools:
            return self._tools
        return self._load_global_tools(self._tools)

    def _resolve_tools_selective(self, prompt: str, override: Optional[List[str]] = None) -> List[Any]:
        """Resolve tools with semantic selection (reduces token cost)."""
        tools = self._resolve_tools(override=override)
        try:
            from core.harness.execution.tool_selector import get_tool_selector
            selector = get_tool_selector()
            return selector.select(prompt, tools)
        except Exception:
            return tools

    @staticmethod
    def _load_global_skills(fallback: List[Any], filter_names: List[str] = None) -> List[Any]:
        try:
            # Pre-filter: if active toolset disallows skills, return empty list
            from core.harness.kernel.execution_context import get_active_workspace_context
            from core.harness.tools.toolsets import resolve_toolset
            ws = get_active_workspace_context()
            active_t = getattr(ws, 'toolset', None) if ws else None
            if active_t:
                policy = resolve_toolset(str(active_t))
                if not policy.skills_allowed:
                    return []

            from core.harness.integration import _ensure_di
            from core.api.facades.skill_tool_facade import get_skill_registry as _import_skill_reg
            di = _ensure_di(); reg = di.resolve("SkillRegistry") if di else _import_skill_reg(); reg = reg() if callable(reg) else reg
            if filter_names:
                return [reg.get(name) for name in filter_names if reg.get(name) is not None]
            names = reg.list_skills()
            return [reg.get(name) for name in names if reg.get(name) is not None]
        except Exception:
            return fallback or []

    @staticmethod
    def _load_global_tools(fallback: List[Any]) -> List[Any]:
        try:
            # DI: using harness-level tool registry resolver
            from core.harness.integration import _resolve_tool_registry; reg = _resolve_tool_registry()
            names = reg.list_tools()
            tools = [reg.get(name) for name in names if reg.get(name) is not None]
            # Pre-filter by active toolset to reduce selector computation
            try:
                from core.harness.kernel.execution_context import get_active_workspace_context
                from core.harness.tools.toolsets import resolve_toolset, is_tool_allowed
                ws = get_active_workspace_context()
                active_t = getattr(ws, 'toolset', None) if ws else None
                if active_t:
                    policy = resolve_toolset(str(active_t))
                    tools = [t for t in tools if is_tool_allowed(policy, getattr(t, 'name', ''))[0]]
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            return tools
        except Exception:
            return fallback or []

    async def run(self, prompt: str, state: Dict[str, Any], stage=None, tools: Optional[List[str]] = None) -> str:
        """Execute one stage via ReActLoop and return the LLM response text.

        This replaces engine._call_llm() for generic pipeline stages.
        The ReActLoop handles: token tracking, hook firing, error recovery,
        and message guard (injection detection).

        Args:
            tools: Per-stage tool whitelist. Overrides __init__ tools when provided.
                   Used by dual-engine to inject stage-specific tools for agent backend.
        """
        # Use per-stage config if provided (Issue 1 fix: per-stage model/skill filtering)
        s = stage if stage is not None else self._stage
        # Determine model_name from stage config or purpose-based routing
        model_name = ""
        if s:
            if s.model:
                model_name = s.model
            elif s.generate_test_plan:
                from core.harness.utils.model_injection import best_model_for_purpose
                model_name = best_model_for_purpose("agent")
        if not model_name:
            from core.harness.utils.model_injection import best_model_for_purpose
            model_name = best_model_for_purpose("agent")
        max_steps = getattr(self._config, 'max_steps_per_stage', 10) if self._config else 1
        # max_tokens: per-stage token budget, derived from pipeline config
        total_budget = getattr(self._config, 'max_tokens_per_run', 100000) if self._config else 100000
        stage_count = max(len(getattr(self._config, 'stages', [])) if self._config else 1, 1)
        import os as _os
        stage_token_min = int(_os.getenv("AIPLAT_STAGE_TOKEN_MIN", "4096"))
        stage_token_max = int(_os.getenv("AIPLAT_STAGE_TOKEN_MAX", "32768"))
        max_tokens = max(stage_token_min, min(total_budget // stage_count, stage_token_max))
        # P1-3: 前序 stage 未用完的预算动态分配给当前 stage
        tokens_bonus = int(state.get("_tokens_bonus", 0) or 0)
        if tokens_bonus > 0:
            max_tokens += tokens_bonus
        skills = self._resolve_skills(stage=s)
        # Auto-skill filter from routing classifier (v2.4): restrict to high-confidence suggestions
        auto_filter = state.get("_auto_skill_filter")
        if auto_filter and isinstance(auto_filter, list) and len(auto_filter) > 0:
            prev_count = len(skills)
            skills = [sk for sk in skills if getattr(sk, 'name', str(sk)) in auto_filter]
            logging.info("auto_skill_filter_applied", extra={
                "filtered_from": prev_count, "filtered_to": len(skills), "filter": auto_filter,
            })
        tools = self._resolve_tools_selective(prompt, override=tools)
        loop = ReActLoop(
            config=LoopConfig(
                max_steps=max_steps,
                max_tokens=max_tokens,
                model_name=model_name,
            ),
            model=self._model,
            tools=tools,
            skills=skills,
        )

        # Read system_prompt from incoming state (set by run_workspace_agent)
        ctx = state.get("context") if isinstance(state.get("context"), dict) else {}
        sys_prompt = state.get("_sys_prompt") or ctx.get("system_prompt", "")

        loop_state = LoopState(
            current=LoopStateEnum.INIT,
            context={
                "task": prompt,
                "system_prompt": sys_prompt,
                "_sys_prompt": sys_prompt,
                "messages": [],
                "_session_id": str(state.get("session_id", "")),
                "_run_id": str(state.get("_run_id", "")),
                "_user_id": "system",
                "_coding_policy_profile": "off",
                "_agent_id": state.get("_agent_id") or (str(s.agent_id or s.id) if s else ""),
                "_agent_namespace": str(s.agent_id or s.id) if s else "",
                "_shared_state_board": state.get("_shared_state_board", []),
                "_enable_query_rewrite": getattr(s, 'enable_query_rewrite', False) if s else False,
                "_max_consecutive_llm_failures": getattr(s, 'max_consecutive_llm_failures', 3),
                "_knowledge_bases": getattr(s, 'knowledge_bases', []) if s else [],
            },
        )

        result = await loop.run(loop_state, LoopConfig(max_steps=max_steps))

        # Background review triggers (best-effort, never block the main flow)
        skill_nudge = int(_os.getenv("AIPLAT_SKILL_NUDGE_INTERVAL", "10"))
        memory_nudge = int(_os.getenv("AIPLAT_MEMORY_NUDGE_INTERVAL", "10"))
        if getattr(loop, '_iters_since_skill', 0) >= skill_nudge and skill_nudge > 0:
            try:
                from core.harness.memory.profile_builder import run_skill_review
                asyncio.create_task(run_skill_review(state))
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        if getattr(loop, '_iters_since_memory', 0) >= memory_nudge and memory_nudge > 0:
            try:
                from core.harness.memory.profile_builder import extract_and_persist_profile
                asyncio.create_task(extract_and_persist_profile(state))
            except Exception as e:
                logging.warning(str(e), exc_info=True)

        # Phase 32: Dynamic orchestration — detect capability gaps and spawn sub-agents
        try:
            reasoning_raw = result.final_state.context.get("reasoning", "") or ""
            if reasoning_raw and len(reasoning_raw) > 50:
                from core.harness.coordination.dynamic_orchestrator import get_dynamic_orchestrator
                orch = get_dynamic_orchestrator()
                gap = await orch.sense_gap(reasoning_raw, str(s.agent_id or s.id) if s else "react")
                if gap:
                    asyncio.create_task(
                        orch.spawn(
                            gap["capability"],
                            f"Task context: {reasoning_raw[:500]}",
                            state.get("session_id", ""),
                            source_agent_id=str(s.agent_id or s.id) if s else "react",
                        )
                    )
        except Exception as e:
            logging.debug("dynamic_orchestrator skipped: %s", e)

        # Extract best output: prefer reasoning (LLM output) > DONE output > observation > action_result
        # reasoning is the actual LLM response; observation is often "No action to execute" filler.
        ctx = result.final_state.context
        reasoning = ctx.get("reasoning", "") or ctx.get("output", "") or ctx.get("observation", "") or ctx.get("action_result", "")

        # ── Merge skill/tool outputs from observations ──
        # Observations contain actual skill execution results (e.g., code_generation output).
        # Without this, _exec_stage only sees reasoning text and misses generated code.
        observations = ctx.get("_observations", [])
        if observations and isinstance(observations, list):
            # Collect non-trivial observations (skip filler like "No action to execute")
            meaningful = [
                str(o) for o in observations
                if isinstance(o, str) and len(o.strip()) > 20
                and "No action" not in str(o)
            ]
            if meaningful:
                delimiter = "\n\n---\n\n"
                all_obs = delimiter.join(meaningful)
                reasoning = f"{reasoning}{delimiter}[OBSERVATION]{delimiter}{all_obs}" if reasoning else all_obs

        step_count = int(getattr(result.final_state, "step_count", 0) or 0)
        tokens_used = int(getattr(result.final_state, "used_tokens", 0) or 0)
        if reasoning:
            state["step_count"] = step_count
        if tokens_used:
            state["_stage_tokens_used"] = tokens_used
        if reasoning:
            return reasoning

        # Fallback: check if loop produced output in error case
        if result.output:
            return str(result.output)

        # FIX A: Surface loop errors instead of returning empty string
        if not result.success and result.error:
            return f"STAGE_ERROR: {result.error}"
        error_info = getattr(result, 'error', None)
        if error_info:
            return f"STAGE_ERROR: {error_info}"

        return ""
