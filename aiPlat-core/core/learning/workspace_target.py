from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from core.governance.changeset import record_changeset


async def ensure_workspace_target(
    *,
    target_type: str,
    target_id: str,
    http_request: Optional[Request] = None,
    engine_skill_manager: Any = None,
    workspace_skill_manager: Any = None,
    engine_agent_manager: Any = None,
    workspace_agent_manager: Any = None,
    store: Any = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Ensure learning artifacts land in workspace scope.
    If target is an engine-level agent/skill, fork a workspace copy and return the new target_id.
    """
    t = str(target_type or "").strip()
    tid = str(target_id or "").strip()
    if not t or not tid:
        raise HTTPException(status_code=400, detail="missing_target")

    # skills
    if t == "skill":
        if workspace_skill_manager:
            try:
                s0 = await workspace_skill_manager.get_skill(tid)
                if s0:
                    return {"target_type": "skill", "target_id": tid, "forked": False}
            except Exception:
                pass
        if not engine_skill_manager:
            if strict:
                raise HTTPException(status_code=503, detail="Engine skill manager not available")
            return {"target_type": "skill", "target_id": tid, "forked": False}
        s1 = await engine_skill_manager.get_skill(tid)
        if not s1:
            # Fail-open for observability/autocapture flows.
            if strict:
                raise HTTPException(status_code=404, detail="skill_not_found")
            return {"target_type": "skill", "target_id": tid, "forked": False}
        if not workspace_skill_manager:
            if strict:
                raise HTTPException(status_code=503, detail="Workspace skill manager not available")
            return {"target_type": "skill", "target_id": tid, "forked": False}

        base_name = str(getattr(s1, "name", None) or "skill").strip() or "skill"
        name = f"{base_name} (workspace)"
        try:
            new_skill = await workspace_skill_manager.create_skill(
                name=name,
                skill_type=str(getattr(s1, "type", None) or "general"),
                description=str(getattr(s1, "description", None) or ""),
                config=getattr(s1, "config", None) or {},
                input_schema=getattr(s1, "input_schema", None) or {},
                output_schema=getattr(s1, "output_schema", None) or {},
                metadata={"lineage": {"forked_from_skill_id": tid, "forked_at": time.time(), "scope": "workspace"}},
            )
        except Exception:
            name = f"{base_name} (workspace {int(time.time())})"
            new_skill = await workspace_skill_manager.create_skill(
                name=name,
                skill_type=str(getattr(s1, "type", None) or "general"),
                description=str(getattr(s1, "description", None) or ""),
                config=getattr(s1, "config", None) or {},
                input_schema=getattr(s1, "input_schema", None) or {},
                output_schema=getattr(s1, "output_schema", None) or {},
                metadata={"lineage": {"forked_from_skill_id": tid, "forked_at": time.time(), "scope": "workspace"}},
            )
        # record governance change (best-effort)
        try:
            from core.api.deps.rbac import actor_from_http

            actor_id = str(actor_from_http(http_request, None).get("actor_id") if http_request else "system")
            await record_changeset(
                store=store,
                name="learning.fork_to_workspace",
                target_type="skill",
                target_id=str(new_skill.id),
                args={"source_scope": "engine", "source_skill_id": tid, "target_scope": "workspace"},
                user_id=actor_id,
            )
        except Exception:
            pass
        return {"target_type": "skill", "target_id": str(new_skill.id), "forked": True, "source_id": tid}

    # agents
    if t == "agent":
        if workspace_agent_manager:
            try:
                a0 = await workspace_agent_manager.get_agent(tid)
                if a0:
                    return {"target_type": "agent", "target_id": tid, "forked": False}
            except Exception:
                pass
        if not engine_agent_manager:
            if strict:
                raise HTTPException(status_code=503, detail="Engine agent manager not available")
            return {"target_type": "agent", "target_id": tid, "forked": False}
        a1 = await engine_agent_manager.get_agent(tid)
        if not a1:
            if strict:
                raise HTTPException(status_code=404, detail="agent_not_found")
            return {"target_type": "agent", "target_id": tid, "forked": False}
        if not workspace_agent_manager:
            if strict:
                raise HTTPException(status_code=503, detail="Workspace agent manager not available")
            return {"target_type": "agent", "target_id": tid, "forked": False}

        base_name = str(getattr(a1, "name", None) or "agent").strip() or "agent"
        name = f"{base_name} (workspace)"
        try:
            new_agent = await workspace_agent_manager.create_agent(
                name=name,
                agent_type=str(getattr(a1, "type", None) or "general"),
                description=str(getattr(a1, "description", None) or ""),
                config=getattr(a1, "config", None) or {},
                metadata={"lineage": {"forked_from_agent_id": tid, "forked_at": time.time(), "scope": "workspace"}},
            )
        except Exception:
            name = f"{base_name} (workspace {int(time.time())})"
            new_agent = await workspace_agent_manager.create_agent(
                name=name,
                agent_type=str(getattr(a1, "type", None) or "general"),
                description=str(getattr(a1, "description", None) or ""),
                config=getattr(a1, "config", None) or {},
                metadata={"lineage": {"forked_from_agent_id": tid, "forked_at": time.time(), "scope": "workspace"}},
            )
        try:
            from core.api.deps.rbac import actor_from_http

            actor_id = str(actor_from_http(http_request, None).get("actor_id") if http_request else "system")
            await record_changeset(
                store=store,
                name="learning.fork_to_workspace",
                target_type="agent",
                target_id=str(new_agent.id),
                args={"source_scope": "engine", "source_agent_id": tid, "target_scope": "workspace"},
                user_id=actor_id,
            )
        except Exception:
            pass
        return {"target_type": "agent", "target_id": str(new_agent.id), "forked": True, "source_id": tid}

    return {"target_type": t, "target_id": tid, "forked": False}
