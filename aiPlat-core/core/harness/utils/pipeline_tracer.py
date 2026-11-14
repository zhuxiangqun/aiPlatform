"""Pipeline tracer — timing and phase tracking for agent pipelines.

Extracted from MaterialsChatAgent's `_trace` closure pattern.
Any agent with a multi-phase execution pipeline can use this.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List


class PipelineTracer:
    """Context manager / callable for tracking pipeline phases with timing."""

    def __init__(self):
        """初始化。
        """
        self._t0: float = time.time()
        self._entries: List[Dict[str, Any]] = []

    def __call__(self, phase: str, detail: str, **meta) -> None:
        """__call__。

        Args:
            phase: phase 参数。
            detail: detail 参数。
            meta: meta 参数。
        """
        t = int((time.time() - self._t0) * 1000)
        entry: Dict[str, Any] = {"phase": phase, "detail": detail, "total_ms": t}
        entry.update(meta)
        self._entries.append(entry)

    @property
    def entries(self) -> List[Dict[str, Any]]:
        """entries。
        """
        return self._entries

    @property
    def elapsed_ms(self) -> int:
        """elapsed_ms。
        """
        return int((time.time() - self._t0) * 1000)
