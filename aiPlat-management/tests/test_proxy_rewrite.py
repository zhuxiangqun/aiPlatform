"""Compatibility rewrites for stale SPA API paths (static frontend proxy)."""
from __future__ import annotations

import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from proxy_server import PLATFORM_URL, ProxyHandler, apply_path_rewrite, MGMT_URL  # noqa: E402


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


def test_other_core_diagnostics_untouched():
    target, path = apply_path_rewrite("/api/core/diagnostics/summary")
    assert target is None
    assert path == "/api/core/diagnostics/summary"


def test_spa_index_injects_chunk_reload():
    blob = b"".join(c for c in ProxyHandler._serve_spa.__code__.co_consts if isinstance(c, bytes))
    assert b"Failed to fetch dynamically imported module" in blob
    assert b"aiplat.chunk_reload" in blob
