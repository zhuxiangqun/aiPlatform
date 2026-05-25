"""
sys_agent_call — Core syscall for dynamic sub-agent delegation.

Allows an agent in the ReAct loop to spawn a sub-agent (from its bound
agent_ids list), delegate a task, and receive a summarized result.

This is the syscall-level entry point for Agent→Agent orchestration.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


async def sys_agent_call(
    subagent_name: str,
    task: str,
    *,
    context: Optional[List[Dict[str, str]]] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Spawn a sub-agent to execute a delegated task.

    Returns:
        {
            "success": bool,
            "output": str,          # summarized result (max 800 chars per §5.26)
            "error": str | None,
            "duration_ms": int,
            "subagent_name": str,
        }
    """
    try:
        from core.apps.agents.subagent.coordinator import get_subagent_coordinator

        coordinator = get_subagent_coordinator()
        result = await coordinator.execute_single(
            subagent_name=subagent_name,
            task=task,
            context=context or [],
        )
        return {
            "success": result.success,
            "output": result.output or "",
            "error": result.error,
            "duration_ms": result.duration_ms,
            "subagent_name": result.subagent_name,
        }
    except ImportError:
        return {
            "success": False,
            "output": "",
            "error": "SubagentCoordinator not available",
            "duration_ms": 0,
            "subagent_name": subagent_name,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "duration_ms": 0,
            "subagent_name": subagent_name,
        }
