"""
FDE application module — agent execution, industry inference, service logic.

This module follows the app-module-layout standard (docs/architecture/app-module-layout.md).
It contains NO HTTP route definitions — those belong in aiPlat-platform/apps/fde/api/.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def run_fde_agent_one_shot(
    agent_id: str,
    skill_filter: list,
    user_message: str,
    extra_context: dict = None,
) -> Optional[dict]:
    """Execute an FDE Agent in one-shot mode with skill subset filtering.
    
    Uses the Agent's own _skills list (set at creation time) rather than 
    context.skills (merge semantics), to avoid interference with other 
    applications that depend on the existing merge behavior (e.g. intents.py).

    Returns None if Agent system is unavailable → caller falls back to 
    direct Skill/API execution.
    """
    _t0 = time.time()
    try:
        from core.apps.agents.base import BaseAgent
        from core.harness.interfaces.agent import AgentContext, AgentConfig
        from core.management.agent_manager import get_agent_manager
        from core.apps.skills import get_skill_registry

        mgr = get_agent_manager()
        agent_info = mgr.get_agent(agent_id)
        if not agent_info:
            logger.warning("fde_agent_missing", extra={"agent_id": agent_id})
            return None

        config = AgentConfig(
            name=agent_id,
            model=agent_info.model or "",
            temperature=0.3,
            max_tokens=2048,
            timeout=60,
        )
        agent = BaseAgent(config)
        skill_registry = get_skill_registry()
        resolved = []
        for sn in skill_filter:
            sk = skill_registry.get(sn)
            if sk:
                resolved.append(sk)
            else:
                logger.warning("fde_skill_not_found", extra={"skill": sn, "agent_id": agent_id})
        agent._skills = resolved

        context = AgentContext(
            session_id=f"fde-{agent_id}-{int(_t0)}",
            user_id="fde",
            messages=[{"role": "user", "content": user_message}],
            metadata=extra_context or {},
        )
        result = await agent.execute(context)
        elapsed_ms = int((time.time() - _t0) * 1000)

        logger.info("fde_agent_execute", extra={
            "agent_id": agent_id,
            "skill_filter": skill_filter,
            "success": result.success,
            "elapsed_ms": elapsed_ms,
        })

        if not result.success:
            return None

        output = result.output
        if isinstance(output, (dict, list)):
            output = json.dumps(output, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "output": str(output)[:8000],
            "agent_id": agent_id,
            "skills_used": skill_filter,
            "elapsed_ms": elapsed_ms,
            "token_usage": result.token_usage,
        }
    except ImportError:
        logger.warning("fde_agent_import_error", extra={"agent_id": agent_id})
        return None
    except Exception:
        logger.error("fde_agent_failed", exc_info=True, extra={"agent_id": agent_id})
        return None
