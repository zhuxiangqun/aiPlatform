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

    def _resolve_tools(self) -> List[Any]:
        if not self._stage:
            return self._load_global_tools(self._tools)
        if self._tools:
            return self._tools
        return self._load_global_tools(self._tools)

    def _resolve_tools_selective(self, prompt: str) -> List[Any]:
        """Resolve tools with semantic selection (reduces token cost)."""
        tools = self._resolve_tools()
        try:
            from core.harness.execution.tool_selector import get_tool_selector
            selector = get_tool_selector()
            return selector.select(prompt, tools)
        except Exception:
            return tools

    @staticmethod
    def _load_global_skills(fallback: List[Any], filter_names: List[str] = None) -> List[Any]:
        try:
            from core.harness.integration import _ensure_di
            from core.api.core_facade import get_skill_registry as _import_skill_reg
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
            return [reg.get(name) for name in names if reg.get(name) is not None]
        except Exception:
            return fallback or []

    async def run(self, prompt: str, state: Dict[str, Any], stage=None) -> str:
        """Execute one stage via ReActLoop and return the LLM response text.

        This replaces engine._call_llm() for generic pipeline stages.
        The ReActLoop handles: token tracking, hook firing, error recovery,
        and message guard (injection detection).
        """
        # Use per-stage config if provided (Issue 1 fix: per-stage model/skill filtering)
        s = stage if stage is not None else self._stage
        # Determine model_name from stage config or purpose-based routing
        model_name = ""
        if s:
            if s.model:
                model_name = s.model
            elif s.generate_test_plan:
                model_name = "agent"  # QA needs reasoning
        if not model_name:
            model_name = "agent"  # default for all stages
        max_steps = getattr(self._config, 'max_steps_per_stage', 10) if self._config else 1
        # max_tokens: per-stage token budget, derived from pipeline config
        total_budget = getattr(self._config, 'max_tokens_per_run', 100000) if self._config else 100000
        stage_count = max(len(getattr(self._config, 'stages', [])) if self._config else 1, 1)
        import os as _os
        stage_token_min = int(_os.getenv("AIPLAT_STAGE_TOKEN_MIN", "4096"))
        stage_token_max = int(_os.getenv("AIPLAT_STAGE_TOKEN_MAX", "32768"))
        max_tokens = max(stage_token_min, min(total_budget // stage_count, stage_token_max))
        skills = self._resolve_skills(stage=s)
        tools = self._resolve_tools_selective(prompt)
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

        loop_state = LoopState(
            current=LoopStateEnum.INIT,
            context={
                "task": prompt,
                "messages": [],
                "_session_id": str(state.get("session_id", "")),
                "_run_id": str(state.get("_run_id", "")),
                "_user_id": "system",
                "_coding_policy_profile": "off",
                "_agent_id": str(s.agent_id or s.id) if s else "",
                "_agent_namespace": str(s.agent_id or s.id) if s else "",
                "_shared_state_board": state.get("_shared_state_board", []),
                "_enable_query_rewrite": getattr(s, 'enable_query_rewrite', False) if s else False,
                "_max_consecutive_llm_failures": getattr(s, 'max_consecutive_llm_failures', 3),
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
            except Exception:
                pass
        if getattr(loop, '_iters_since_memory', 0) >= memory_nudge and memory_nudge > 0:
            try:
                from core.harness.memory.profile_builder import extract_and_persist_profile
                asyncio.create_task(extract_and_persist_profile(state))
            except Exception:
                pass

        # Extract best output: prefer DONE output > observation > reasoning > action_result
        ctx = result.final_state.context
        reasoning = ctx.get("output", "") or ctx.get("observation", "") or ctx.get("reasoning", "") or ctx.get("action_result", "")
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
