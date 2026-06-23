"""
Tool self-tests: verify core logic of guard_frontend.py is correct.

Tests:
  - _normalize_path: query string stripping, lowercase, trailing slash
  - _paths_match: exact, parameterized, different param names, segment count mismatch
  - route extraction: mount prefix + router self-prefix composition
"""
import sys
from pathlib import Path
import pytest

# Add workspace root to path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from scripts.guard_frontend import (
    _normalize_path,
    _paths_match,
    _build_mount_prefixes,
    _extract_frontend_paths,
    _extract_backend_routes,
)


class TestNormalizePath:

    def test_lowercase(self):
        assert _normalize_path("/API/Platform/Health") == "/api/platform/health"

    def test_strip_trailing_slash(self):
        assert _normalize_path("/health/") == "/health"

    def test_strip_query_string(self):
        assert _normalize_path("/documents?limit=100") == "/documents"

    def test_strip_query_and_slash(self):
        result = _normalize_path("/api/?x=1")
        assert result in ("/api", "/api/"), f"Unexpected: {result}"


class TestPathsMatch:

    def test_exact_match(self):
        assert _paths_match("/platform/health", "/platform/health")

    def test_case_insensitive(self):
        assert _paths_match("/Platform/Health", "/platform/health")

    def test_trailing_slash_insensitive(self):
        assert _paths_match("/health/", "/health")

    def test_parameterized_match_same_name(self):
        assert _paths_match(
            "/documents/{doc_id}/reingest",
            "/documents/{doc_id}/reingest",
        )

    def test_parameterized_match_diff_names(self):
        assert _paths_match(
            "/documents/{id}/reingest",
            "/documents/{doc_id}/reingest",
        )

    def test_angle_bracket_params(self):
        assert _paths_match(
            "/releases/{id}/publish",
            "/releases/<release_id>/publish",
        )

    def test_colon_params(self):
        assert _paths_match(
            "/users/:user_id/settings",
            "/users/:uid/settings",
        )

    def test_segment_count_mismatch(self):
        assert not _paths_match(
            "/documents/{id}",
            "/documents/{id}/reingest",
        )

    def test_different_fixed_segments(self):
        assert not _paths_match(
            "/platform/documents/{id}",
            "/platform/kb/documents/{id}",
        )

    def test_query_string_normalized_before_match(self):
        """Paths with query strings should be normalized before matching."""
        assert _paths_match("/api?limit=100", "/api")


class TestMountPrefixes:

    def test_returns_dict(self):
        prefixes = _build_mount_prefixes()
        assert isinstance(prefixes, dict), f"Expected dict, got {type(prefixes)}"

    def test_core_api_prefix_exists(self):
        prefixes = _build_mount_prefixes()
        core_prefixes = [v for v in prefixes.values() if "/api/core" in v]
        assert len(core_prefixes) > 0, "Expected at least one /api/core prefix mapping"

    def test_key_router_files_mapped(self):
        prefixes = _build_mount_prefixes()
        key_files = ["wiki.py", "mcp_admin.py", "workspace_agents.py", "plugins.py"]
        missing = [f for f in key_files if f not in prefixes]
        assert missing == [], f"Missing prefix mappings: {missing}"


class TestBackendRouteExtraction:

    def test_extracts_known_route(self):
        routes = _extract_backend_routes()
        assert len(routes) > 100, f"Expected >100 routes, got {len(routes)}"

    def test_wiki_routes_prefixed(self):
        routes = _extract_backend_routes()
        wiki_routes = [r for r in routes if "/api/core/wiki/" in _normalize_path(r["path"])]
        assert len(wiki_routes) > 5, (
            f"Expected >5 wiki routes with /api/core/wiki/ prefix, got {len(wiki_routes)}"
        )

    def test_mcp_routes_prefixed(self):
        routes = _extract_backend_routes()
        mcp_routes = [r for r in routes if "mcp" in r["path"].lower()]
        assert len(mcp_routes) > 3, (
            f"Expected >3 MCP routes, got {len(mcp_routes)}"
        )

    def test_platform_kb_routes_present(self):
        routes = _extract_backend_routes()
        kb_routes = [r for r in routes if "/platform/kb/" in _normalize_path(r["path"])]
        assert len(kb_routes) > 10, (
            f"Expected >10 /platform/kb/ routes, got {len(kb_routes)}"
        )


class TestFrontendPathExtraction:

    def test_extracts_kbapi_paths(self):
        paths = _extract_frontend_paths()
        assert len(paths) > 50, f"Expected >50 frontend paths, got {len(paths)}"

    def test_method_detection_apiClient(self):
        paths = _extract_frontend_paths()
        methods = set(p["method"] for p in paths)
        assert "POST" in methods, f"Expected POST among methods: {methods}"
        assert "GET" in methods, f"Expected GET among methods: {methods}"

    def test_no_external_urls(self):
        paths = _extract_frontend_paths()
        for p in paths:
            assert "http://" not in p["path"], f"External URL found: {p['path']}"
            assert "https://" not in p["path"], f"External URL found: {p['path']}"

    def test_all_paths_absolute(self):
        paths = _extract_frontend_paths()
        for p in paths:
            assert p["path"].startswith("/"), f"Path not absolute: {p['path']}"
