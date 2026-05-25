"""
EvalRunner — independent evaluator that uses a dedicated model separate from
the stage execution model.

Design principle (harness/CLAUDE.md §5.17, 5.23):
  Evaluation MUST be performed by an independent component, not the same
  agent that produced the output.  This breaks positive feedback loops
  ("AI self-evaluating → error amplification" — cybernetic control theory).

This module is the path to decouple `_tri_evaluate` from `_stage_runner`:
  _tri_evaluate() → EvalRunner.run() → ReActLoop (dedicated eval model)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum

_log = logging.getLogger("pipeline_engine.eval_runner")


class EvalRunner:
    def __init__(self, model=None, pipeline_config=None):
        self._model = model
        self._config = pipeline_config

    async def run(self, prompt: str, state: Dict[str, Any]) -> str:
        max_steps = 1
        max_tokens = int(os.getenv("AIPLAT_EVAL_MAX_TOKENS", "8192"))
        loop = ReActLoop(
            config=LoopConfig(
                max_steps=max_steps,
                max_tokens=max_tokens,
                model_name="eval",
            ),
            model=self._model,
            tools=[],
            skills=[],
        )

        loop_state = LoopState(
            current=LoopStateEnum.INIT,
            context={
                "task": prompt,
                "messages": [],
                "_session_id": str(state.get("session_id", "")),
                "_user_id": "system",
                "_coding_policy_profile": "off",
            },
        )

        result = await loop.run(loop_state, LoopConfig(max_steps=max_steps))
        ctx = result.final_state.context
        output = ctx.get("output", "") or ctx.get("observation", "") or ctx.get("reasoning", "")
        if output:
            return output
        if result.output:
            return str(result.output)
        if not result.success and result.error:
            return f"EVAL_ERROR: {result.error}"
        return ""
