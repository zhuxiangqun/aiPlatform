"""Runtime context injection into system prompts.

Phase 10.1-10.3: injects RunContext as a [运行时上下文] system message
between domain prompt and base role in the system prompt stack.

Moved from materials_chat.py Phase 1 refactoring.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional


def inject_run_context(
    system_msgs: List[Dict[str, str]],
    run_context: Optional[dict],
) -> List[Dict[str, str]]:
    """Inject runtime operational context into system prompt messages.

    Args:
        system_msgs: Current system message list (mutated in-place).
        run_context: RunContext dict, RunContext instance, or None.

    Returns:
        The same list, with context appended if available.
    """
    if not run_context:
        return system_msgs
    try:
        from core.harness.kernel.types import RunContext

        if isinstance(run_context, RunContext):
            ctx_text = run_context.to_compact()
        elif isinstance(run_context, dict):
            ctx_text = RunContext(**run_context).to_compact()
        else:
            ctx_text = str(run_context)
        system_msgs.append({"role": "system", "content": f"[运行时上下文] {ctx_text}"})
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return system_msgs
