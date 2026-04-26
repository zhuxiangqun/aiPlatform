from __future__ import annotations

import time
from typing import Any, Dict, Optional


def autosmoke_job_id(resource_type: str, resource_id: str) -> str:
    return f"autosmoke-{str(resource_type).strip().lower()}:{str(resource_id).strip()}"


async def set_resource_verification(
    *,
    resource_type: str,
    resource_id: str,
    verification: Dict[str, Any],
    workspace_agent_manager: Any = None,
    workspace_skill_manager: Any = None,
    workspace_mcp_manager: Any = None,
) -> None:
    rtype = str(resource_type or "").strip().lower()
    rid = str(resource_id or "").strip()
    if not rtype or not rid:
        return
    try:
        if rtype == "agent" and workspace_agent_manager:
            await workspace_agent_manager.update_agent(rid, metadata={"verification": verification})
        elif rtype == "skill" and workspace_skill_manager:
            await workspace_skill_manager.update_skill(rid, metadata={"verification": verification})
        elif rtype == "mcp" and workspace_mcp_manager:
            workspace_mcp_manager.update_server(rid, metadata={"verification": verification})
    except Exception:
        return


async def mark_resource_pending(
    *,
    resource_type: str,
    resource_id: str,
    workspace_agent_manager: Any = None,
    workspace_skill_manager: Any = None,
    workspace_mcp_manager: Any = None,
) -> None:
    await set_resource_verification(
        resource_type=resource_type,
        resource_id=resource_id,
        verification={"status": "pending", "updated_at": time.time(), "source": "autosmoke"},
        workspace_agent_manager=workspace_agent_manager,
        workspace_skill_manager=workspace_skill_manager,
        workspace_mcp_manager=workspace_mcp_manager,
    )


async def apply_autosmoke_result(
    *,
    resource_type: str,
    resource_id: str,
    job_run: Dict[str, Any],
    workspace_agent_manager: Any = None,
    workspace_skill_manager: Any = None,
    workspace_mcp_manager: Any = None,
) -> None:
    st = str((job_run or {}).get("status") or "")
    jid = autosmoke_job_id(resource_type, resource_id)
    ver = {
        "status": "verified" if st == "completed" else "failed",
        "updated_at": time.time(),
        "source": "autosmoke",
        "job_id": jid,
        "job_run_id": str((job_run or {}).get("id") or ""),
        "reason": str((job_run or {}).get("error") or ""),
    }
    await set_resource_verification(
        resource_type=resource_type,
        resource_id=resource_id,
        verification=ver,
        workspace_agent_manager=workspace_agent_manager,
        workspace_skill_manager=workspace_skill_manager,
        workspace_mcp_manager=workspace_mcp_manager,
    )


async def get_resource_verification(
    *,
    resource_type: str,
    resource_id: str,
    workspace_agent_manager: Any = None,
    workspace_skill_manager: Any = None,
    workspace_mcp_manager: Any = None,
) -> Optional[Dict[str, Any]]:
    rtype = str(resource_type or "").strip().lower()
    rid = str(resource_id or "").strip()
    if not rtype or not rid:
        return None
    try:
        if rtype == "agent" and workspace_agent_manager:
            a = await workspace_agent_manager.get_agent(rid)
            return (getattr(a, "metadata", None) or {}).get("verification")
        if rtype == "skill" and workspace_skill_manager:
            s = await workspace_skill_manager.get_skill(rid)
            return (getattr(s, "metadata", None) or {}).get("verification")
        if rtype == "mcp" and workspace_mcp_manager:
            m = workspace_mcp_manager.get_server(rid)
            return (getattr(m, "metadata", None) or {}).get("verification")
    except Exception:
        return None
    return None

