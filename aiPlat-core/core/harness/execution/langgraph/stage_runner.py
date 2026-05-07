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
    """Run a single pipeline stage via the shared ReActLoop harness."""

    def __init__(
        self,
        stage: Optional[PipelineStageConfig] = None,
        model: Any = None,
        tools: Optional[List[Any]] = None,
        skills: Optional[List[Any]] = None,
    ):
        self._stage = stage
        self._model = model
        self._tools = tools or []
        self._skills = skills or []

    async def run(self, prompt: str, state: Dict[str, Any]) -> str:
        """Execute one stage via ReActLoop and return the LLM response text.

        This replaces engine._call_llm() for generic pipeline stages.
        The ReActLoop handles: token tracking, hook firing, error recovery,
        and message guard (injection detection).
        """
        # Determine model_name from stage config or purpose-based routing
        model_name = ""
        if self._stage:
            if self._stage.model:
                model_name = self._stage.model
            elif self._stage.generate_test_plan:
                model_name = "agent"  # QA needs reasoning
            elif getattr(self._stage, 'uses_code_skill', False) is False and not self._stage.model:
                # Generic non-code stages that need reasoning: route to agent model
                model_name = "agent"  # resolved via ModelRegistry purpose map
        loop = ReActLoop(
            config=LoopConfig(
                max_steps=1,  # single-step: Reason only (no tool calls expected)
                max_tokens=8192,
                model_name=model_name,
            ),
            model=self._model,
            tools=self._tools,
            skills=self._skills,
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
                "_max_consecutive_llm_failures": getattr(self._stage, 'max_consecutive_llm_failures', 3),
            },
        )

        result = await loop.run(loop_state, LoopConfig(max_steps=1))

        # Extract the final reasoning output (the LLM's text response)
        reasoning = result.final_state.context.get("reasoning", "")
        if reasoning:
            return reasoning

        # Fallback: check if loop produced output in error case
        if result.output:
            return str(result.output)

        return ""
