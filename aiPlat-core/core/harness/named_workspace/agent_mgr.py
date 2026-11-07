"""Per-named-workspace AgentManager cache (explicit ctx; no ambient-only truth)."""
from __future__ import annotations

import logging
import threading
from typing import Dict

from core.harness.named_workspace.resolve import (
    NamedWorkspaceContext,
    reset_active_named_workspace,
    set_active_named_workspace,
)
from core.management.agent_manager import AgentManager

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Dict[str, AgentManager] = {}


def agent_manager_for(ctx: NamedWorkspaceContext) -> AgentManager:
    """Return AgentManager loaded from ctx.agents_dir (cached by workspace_id)."""
    wid = ctx.workspace_id
    with _lock:
        mgr = _cache.get(wid)
        if mgr is not None:
            return mgr
        token = set_active_named_workspace(ctx)
        try:
            mgr = AgentManager(seed=False, scope="workspace")
        finally:
            reset_active_named_workspace(token)
        _cache[wid] = mgr
        logger.debug("named_workspace agent manager cached id=%s path=%s", wid, ctx.agents_dir)
        return mgr


def invalidate_agent_manager(workspace_id: str | None = None) -> None:
    with _lock:
        if workspace_id:
            _cache.pop(workspace_id, None)
        else:
            _cache.clear()
