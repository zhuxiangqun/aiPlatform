"""Task-scoped model hold.

Lock is off unless ``AIPLAT_TASK_MODEL_LOCK=1``. While off, selection stays on
the existing pipeline (``held_model_for_task`` returns None).
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional


def task_model_lock_enabled() -> bool:
    """task_model_lock_enabled。
    """
    return os.environ.get("AIPLAT_TASK_MODEL_LOCK", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def bind_task_model_scope(task_id: str = "") -> Optional[str]:
    """bind_task_model_scope。

    Args:
        task_id: task 标识。
    """
    if not task_model_lock_enabled():
        return None
    held = current_task_id()
    return held or str(task_id or "") or None


def reset_task_model_scope(token: Any = None) -> None:
    """reset_task_model_scope。

    Args:
        token: token 参数。
    """
    return None


def current_task_id() -> str:
    """current_task_id。
    """
    return ""


def note_tool_outcome(status: str = "", detail: str = "") -> None:
    """note_tool_outcome。

    Args:
        status: status 参数。
        detail: detail 参数。
    """
    return None


def held_model_for_task(
    purpose: str,
    select_fn: Callable[..., str],
    messages: Any = None,
) -> Optional[str]:
    """Return None so the caller uses the normal model pipeline.

    Args:
        purpose: purpose 参数。
        select_fn: select_fn 参数。
        messages: messages 参数。
    """
    return None


def finish_task_model_scope(task_id: str = "", success: bool = False) -> None:
    """finish_task_model_scope。

    Args:
        task_id: task 标识。
        success: success 参数。
    """
    return None


def summarize_task_model_routes(*, limit: int = 500) -> Dict[str, Any]:
    """summarize_task_model_routes。

    Args:
        limit: 返回条数上限。
    """
    _ = limit
    return {"available": False, "routes": [], "held": 0}
