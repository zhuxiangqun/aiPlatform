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

    @staticmethod
    def _load_global_skills(fallback: List[Any], filter_names: List[str] = None) -> List[Any]:
        try:
            # DI: using harness-level registry resolver
# from core.harness.integration import _resolve_or_import  -- called at runtime
            from core.harness.integration import _ensure_di; di = _ensure_di(); reg = di.resolve("SkillRegistry") if di else _import_skill_reg(); reg = reg() if callable(reg) else reg
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
        skills = self._resolve_skills(stage=s)
        tools = self._resolve_tools()
        loop = ReActLoop(
            config=LoopConfig(
                max_steps=max_steps,
                max_tokens=8192,
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
                "_user_id": "system",
                "_coding_policy_profile": "off",
                # Pass stage degradation config to loop for per-stage failure control
                "_max_consecutive_llm_failures": getattr(s, 'max_consecutive_llm_failures', 3),
            },
        )

        result = await loop.run(loop_state, LoopConfig(max_steps=max_steps))

        # Extract best output: prefer DONE output > observation > reasoning > action_result
        ctx = result.final_state.context
        reasoning = ctx.get("output", "") or ctx.get("observation", "") or ctx.get("reasoning", "") or ctx.get("action_result", "")
        step_count = int(getattr(result.final_state, "step_count", 0) or 0)
        if reasoning:
            state["step_count"] = step_count
        if reasoning:
            return reasoning

        # Fallback: check if loop produced output in error case
        if result.output:
            return str(result.output)

        return ""
