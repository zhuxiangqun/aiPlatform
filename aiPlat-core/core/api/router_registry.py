"""Router Registry — decouples server startup from individual platform router imports.

Platform modules register their FastAPI routers here; the core server calls
`mount_all(app)` to mount them without knowing about platform-specific modules.

This breaks the core→platform reverse dependency in server startup.
"""

from __future__ import annotations

import logging
from typing import Any, List, Tuple

_log = logging.getLogger(__name__)

_registry: List[Tuple[str, Any]] = []


def register(prefix: str, router: Any) -> None:
    """Register a router to be mounted at server startup.

    Called by platform modules (e.g., fde/__init__.py, workbench/__init__.py)
    during import. The core server calls mount_all() which includes all
    registered routers via app.include_router().

    Args:
        prefix: URL prefix for the router (e.g., "/api/platform/apps/fde")
        router: FastAPI APIRouter instance
    """
    _registry.append((prefix, router))
    _log.debug("Router registered: %s", prefix)


def mount_all(app: Any) -> None:
    """Mount all registered routers onto the given FastAPI app.

    Called from server.py startup after all platform modules have been imported.

    Args:
        app: FastAPI application instance
    """
    for prefix, router in _registry:
        app.include_router(router, prefix=prefix)
        _log.info("Mounted router: %s", prefix)
    _log.info("All %d routers mounted", len(_registry))
