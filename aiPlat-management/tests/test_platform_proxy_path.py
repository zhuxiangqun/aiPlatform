"""Management platform proxy path mapping (apps → /api/platform/apps)."""
from __future__ import annotations

from management.api.proxy import _platform_upstream_path


def test_apps_module_uses_api_platform_prefix():
    assert _platform_upstream_path("apps/code-review-gold/evaluate") == (
        "/api/platform/apps/code-review-gold/evaluate"
    )
    assert _platform_upstream_path("apps") == "/api/platform/apps"
    assert _platform_upstream_path("/apps/fde/status") == "/api/platform/apps/fde/status"


def test_legacy_kb_stays_under_platform():
    assert _platform_upstream_path("kb/stats") == "/platform/kb/stats"
    assert _platform_upstream_path("documents/ingest") == "/platform/documents/ingest"
    assert _platform_upstream_path("auth/users") == "/platform/auth/users"
