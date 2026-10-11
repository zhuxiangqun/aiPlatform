"""Compatibility rewrites for stale SPA API paths (static frontend proxy)."""
from __future__ import annotations

import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from proxy_server import (  # noqa: E402
    PLATFORM_URL,
    PROXY_ROUTES,
    ProxyHandler,
    _apps_yaml_platform_routes,
    apply_path_rewrite,
    MGMT_URL,
)


def test_code_review_gold_routes_to_platform():
    """Governance Gold CTA POST must not land on mgmt (wrong /platform/apps)."""
    assert PROXY_ROUTES.get("/api/platform/apps/code-review-gold") == PLATFORM_URL
    handler = ProxyHandler.__new__(ProxyHandler)
    target, precise = handler._get_target("/api/platform/apps/code-review-gold/evaluate")
    assert target == PLATFORM_URL
    assert precise is True


def test_apps_yaml_drives_platform_app_routes():
    """New apps modules should pin via apps.yaml, not only hand-written statics."""
    routes = _apps_yaml_platform_routes()
    assert routes.get("/api/platform/apps/fde") == PLATFORM_URL
    assert routes.get("/api/platform/apps/code-review-gold") == PLATFORM_URL
    assert routes.get("/api/platform/apps/kb-eval") == PLATFORM_URL
    assert routes.get("/api/platform/apps/eval") == PLATFORM_URL


def test_doctor_core_prefix_rewrites_to_management():
    target, path = apply_path_rewrite("/api/core/diagnostics/doctor")
    assert target == MGMT_URL
    assert path == "/api/diagnostics/doctor"


def test_doctor_query_preserved():
    target, path = apply_path_rewrite("/api/core/diagnostics/doctor?refresh=1")
    assert target == MGMT_URL
    assert path == "/api/diagnostics/doctor?refresh=1"


def test_eval_observability_rewrites_to_platform():
    target, path = apply_path_rewrite("/api/governance/eval-observability")
    assert target == PLATFORM_URL
    assert path == "/governance/eval-observability"


def test_org_harness_rewrites_to_platform():
    target, path = apply_path_rewrite("/api/governance/org-harness")
    assert target == PLATFORM_URL
    assert path == "/governance/org-harness"


def test_repo_health_scan_rewrites_to_platform():
    """Duty-board Repo health CTA must hit platform, not mgmt /api catch-all."""
    target, path = apply_path_rewrite("/api/governance/repo-health/scan")
    assert target == PLATFORM_URL
    assert path == "/governance/repo-health/scan"
    target2, path2 = apply_path_rewrite("/api/governance/repo-health?x=1")
    assert target2 == PLATFORM_URL
    assert path2 == "/governance/repo-health?x=1"


def test_governance_prefix_exact_and_subpath():
    """Prefix rewrite: exact /api/governance and /api/governance/* both → platform."""
    t0, p0 = apply_path_rewrite("/api/governance")
    assert t0 == PLATFORM_URL
    assert p0 == "/governance"
    t1, p1 = apply_path_rewrite("/api/governance/jobs")
    assert t1 == PLATFORM_URL
    assert p1 == "/governance/jobs"


def test_other_core_diagnostics_untouched():
    target, path = apply_path_rewrite("/api/core/diagnostics/summary")
    assert target is None
    assert path == "/api/core/diagnostics/summary"


def test_spa_index_injects_chunk_reload():
    blob = b"".join(c for c in ProxyHandler._serve_spa.__code__.co_consts if isinstance(c, bytes))
    assert b"Failed to fetch dynamically imported module" in blob
    assert b"aiplat.chunk_reload" in blob
