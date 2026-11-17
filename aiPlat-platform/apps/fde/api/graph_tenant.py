"""FDE API GraphIndex tenant resolution (N09 K31).

Shared helper so platform FDE routers do not invent parallel tenant paths.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def fde_graph_tenant(request: Any = None) -> str:
    """Resolve tenant for FDE API GraphIndex loads.

    Prefers HTTP request identity when available, else ActiveRequestContext
    via CoreFacade (platform must not import core.harness directly).

    Args:
        request: Optional FastAPI Request.

    Returns:
        非空租户 id。
    """
    if request is not None:
        try:
            from auth.request_identity import resolve_request_tenant

            tid = str(resolve_request_tenant(request) or "").strip()
            if tid:
                return tid
        except Exception:
            # 为什么：身份解析失败时回退 ActiveRequestContext，不可静默吞掉可观测性
            logger.debug("fde_graph_tenant: resolve_request_tenant failed", exc_info=True)
    from core.api.core_facade import resolve_graph_tenant

    return resolve_graph_tenant()
