"""Prompt Plan-chain exam — thin wrapper over ``typed_plan_exam`` (§0.8 P0).

Distinct from page/DB ``prompt_eval_ops``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from core.apps.eval.service.typed_plan_exam import (
    load_prompt_set_json,
    score_prompt_output,
    run_typed_plan_exam,
)

__all__ = [
    "load_prompt_set_json",
    "score_prompt_output",
    "run_prompt_plan_exam",
]


async def run_prompt_plan_exam(
    *,
    object_id: str = "prompt_under_test",
    set_ids: Optional[Sequence[str]] = None,
    purpose: Optional[Sequence[str]] = None,
    include_special: bool = False,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
) -> Dict[str, Any]:
    """Compile Plan for prompt + execute selected ``prompt/*`` sets."""
    return await run_typed_plan_exam(
        object_type="prompt",
        object_id=object_id or "prompt_under_test",
        set_ids=set_ids,
        purpose=purpose,
        include_special=include_special,
        live=live,
        model=model,
        max_tasks_per_set=max_tasks_per_set,
        source_refs=["prompt_plan_ops"],
    )
