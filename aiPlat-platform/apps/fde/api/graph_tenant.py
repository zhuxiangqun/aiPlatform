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


def _router_domain(method: str, attr: str) -> str:
    """Resolve a DomainRouter domain helper via CoreFacade (no call-site literals).

    Args:
        method: DomainRouter 方法名（如 terms_domain）。
        attr: 回落类常量名（PLATFORM_*_DOMAIN）。
    """
    from core.api.core_facade import get_domain_router

    router = get_domain_router()
    fn = getattr(router, method, None)
    if callable(fn):
        did = str(fn() or "").strip()
        if did:
            return did
    # 为什么：方法异常空串时回落 SSOT 类常量，避免再引入域名字面量
    for obj in (router, type(router)):
        did = str(getattr(obj, attr, "") or "").strip()
        if did:
            return did
    logger.debug("fde domain resolve empty method=%s attr=%s", method, attr)
    return ""


def fde_graph_domain() -> str:
    """Resolve FDE tracking domain for GraphIndex loads (N09 K38).

    Uses CoreFacade ``get_domain_router().tracking_domain()`` so platform
    routers do not hardcode the tracking domain string.

    Returns:
        非空 domain id（SSOT: DomainRouter.tracking_domain）。
    """
    return _router_domain("tracking_domain", "PLATFORM_TRACKING_DOMAIN")


def fde_terms_domain() -> str:
    """Resolve enterprise-terms domain for FDE GraphIndex loads (N09 K39).

    Returns:
        非空 domain id。
    """
    return _router_domain("terms_domain", "PLATFORM_TERMS_DOMAIN")


def fde_atom_domain() -> str:
    """Resolve knowledge-atom domain for FDE GraphIndex loads (N09 K39).

    Returns:
        非空 domain id。
    """
    return _router_domain("knowledge_atom_domain", "PLATFORM_ATOM_DOMAIN")


def fde_kb_domain() -> str:
    """Resolve default KB domain for FDE GraphIndex loads (N09 K39).

    Returns:
        非空 domain id。
    """
    return _router_domain("default_kb_domain", "PLATFORM_KB_DOMAIN")
