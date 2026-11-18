"""FDE API GraphIndex tenant + platform domain resolution (N09 K31/K38/K39).

Shared helpers so platform FDE routers do not invent parallel tenant paths
or hardcode tracking/terms/atom/kb domain strings.
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


def fde_graph_domain() -> str:
    """Resolve FDE tracking domain for GraphIndex loads (N09 K38).

    Uses CoreFacade ``get_domain_router().tracking_domain()`` so platform
    routers do not hardcode the tracking domain string.

    Returns:
        非空 domain id（SSOT: DomainRouter.tracking_domain）。
    """
    from core.api.core_facade import get_domain_router

    router = get_domain_router()
    did = str(router.tracking_domain() or "").strip()
    if did:
        return did
    # 为什么：tracking_domain 契约应永非空；若异常空串则回落类常量，避免 GraphIndex.load("")
    return str(getattr(router, "PLATFORM_TRACKING_DOMAIN", "") or "fde-delivery")


def fde_terms_domain() -> str:
    """Resolve enterprise-terms domain for FDE GraphIndex loads (N09 K39).

    Returns:
        非空 domain id。
    """
    from core.api.core_facade import get_domain_router

    router = get_domain_router()
    did = str(router.terms_domain() or "").strip()
    return did or str(getattr(router, "PLATFORM_TERMS_DOMAIN", "") or "enterprise-terms")


def fde_atom_domain() -> str:
    """Resolve knowledge-atom domain for FDE GraphIndex loads (N09 K39).

    Returns:
        非空 domain id。
    """
    from core.api.core_facade import get_domain_router

    router = get_domain_router()
    did = str(router.knowledge_atom_domain() or "").strip()
    return did or str(getattr(router, "PLATFORM_ATOM_DOMAIN", "") or "knowledge-atom")


def fde_kb_domain() -> str:
    """Resolve default KB domain for FDE GraphIndex loads (N09 K39).

    Returns:
        非空 domain id。
    """
    from core.api.core_facade import get_domain_router

    router = get_domain_router()
    did = str(router.default_kb_domain() or "").strip()
    return did or str(getattr(router, "PLATFORM_KB_DOMAIN", "") or "ai-knowledge")

