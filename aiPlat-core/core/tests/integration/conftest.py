"""Integration-test fixtures.

gate_policies / change_control routers were migrated from core to aiPlat-platform
(per architecture contract). These cross-layer integration tests build the core
app (which initializes the core kernel runtime the platform handlers depend on)
and then mount the migrated platform routers under /api so the tests can reach
them at /api/platform/...  (matching production where the platform server serves
/api/platform/* and the frontend calls those paths — see ① Part B path alignment).
"""
import sys
from pathlib import Path

import pytest


def _ensure_platform_on_path() -> None:
    platform = Path(__file__).resolve().parents[4] / "aiPlat-platform"
    if platform.exists() and str(platform) not in sys.path:
        sys.path.insert(0, str(platform))


@pytest.fixture
def mount_platform_governance():
    """Return a function that mounts the migrated platform governance/change-control
    routers onto a (core) test app under /api → /api/platform/... ."""
    def _mount(app) -> None:
        _ensure_platform_on_path()
        from api.routers.gate_policies import router as gp_router
        from api.routers.change_control import router as cc_router
        app.include_router(gp_router, prefix="/api")
        app.include_router(cc_router, prefix="/api")
    return _mount
