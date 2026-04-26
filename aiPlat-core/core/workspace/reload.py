from __future__ import annotations

from typing import Any, Dict, Optional


def rebuild_workspace_managers(
    *,
    engine_agent_manager: Any,
    engine_skill_manager: Any,
    engine_mcp_manager: Any,
) -> Dict[str, Any]:
    """
    Rebuild workspace managers from filesystem with engine reserved IDs/names.
    Used after operations that modify ~/.aiplat directly (e.g., package install).
    """
    from core.management.agent_manager import AgentManager
    from core.management.skill_manager import SkillManager
    from core.management.mcp_manager import MCPManager

    out: Dict[str, Any] = {}
    try:
        if engine_agent_manager:
            out["workspace_agent_manager"] = AgentManager(seed=False, scope="workspace", reserved_ids=set(engine_agent_manager.get_agent_ids()))
    except Exception:
        out["workspace_agent_manager"] = None
    try:
        if engine_skill_manager:
            out["workspace_skill_manager"] = SkillManager(seed=False, scope="workspace", reserved_ids=set(engine_skill_manager.get_skill_ids()))
    except Exception:
        out["workspace_skill_manager"] = None
    try:
        if engine_mcp_manager is not None:
            out["workspace_mcp_manager"] = MCPManager(scope="workspace", reserved_names=set(engine_mcp_manager.get_server_names()) if engine_mcp_manager else set())
    except Exception:
        out["workspace_mcp_manager"] = None
    return out


async def rebuild_workspace_managers_into_runtime(*, runtime: Any) -> Dict[str, Any]:
    """
    Best-effort: rebuild workspace managers and update KernelRuntime fields in-place.
    Returns the created managers (or None entries).
    """
    out = rebuild_workspace_managers(
        engine_agent_manager=getattr(runtime, "agent_manager", None),
        engine_skill_manager=getattr(runtime, "skill_manager", None),
        engine_mcp_manager=getattr(runtime, "mcp_manager", None),
    )
    for k, v in out.items():
        try:
            setattr(runtime, k, v)
        except Exception:
            pass
    return out

