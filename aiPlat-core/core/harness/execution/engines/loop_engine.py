"""
LoopEngine (Phase 5.0).

Behavior-preserving wrapper around existing agent.execute(context) that allows
HarnessIntegration to route all agent executions through a single router+engine layer.
"""

from __future__ import annotations

from typing import Any


class LoopEngine:
    """LoopEngine。"""
    name = "loop"

    async def execute_agent(self, agent: Any, context: Any) -> Any:
        """execute_agent。

        Args:
            agent: agent 参数。
            context: context 参数。
        """
        return await agent.execute(context)

