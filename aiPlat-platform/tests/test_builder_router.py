"""Tests for builder.py router — Builder API endpoint completeness and compliance."""
import sys
import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

import pytest

BUILDER_PATH = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"


class TestBuilderRouterStatic:
    """Static analysis — no imports needed."""

    def test_file_exists(self):
        assert BUILDER_PATH.exists(), f"builder.py not found at {BUILDER_PATH}"

    def test_no_dead_imports(self):
        tree = ast.parse(BUILDER_PATH.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        # Should NOT import from dead builder_session
        assert "builder_session" not in [i or "" for i in imports], \
            "Must not import from deprecated builder_session"

    def test_has_deprecation_helper(self):
        content = BUILDER_PATH.read_text()
        assert "_deprecation_header" in content, "Missing deprecation header dict"
        assert "_legacy_response" in content, "Missing _legacy_response helper"

    def test_has_rollback_prd_endpoint(self):
        content = BUILDER_PATH.read_text()
        assert "rollback-prd" in content, "Missing rollback-prd endpoint"

    def test_has_all_project_endpoints(self):
        content = BUILDER_PATH.read_text()
        required = ["/projects/{project_id}/state", "/projects/{project_id}/chat",
                    "/projects/{project_id}/confirm", "/projects/{project_id}/start",
                    "/projects/{project_id}/approve", "/projects/{project_id}/reject",
                    "/projects/{project_id}/rollback/{stage_id:path}",
                    "/projects/{project_id}/fix", "/projects/{project_id}/resume"]
        for ep in required:
            assert ep in content, f"Missing endpoint: {ep}"

    def test_has_team_endpoints(self):
        content = BUILDER_PATH.read_text()
        assert "/teams" in content, "Missing team CRUD endpoints"

    def test_has_legacy_sessions(self):
        content = BUILDER_PATH.read_text()
        assert "/sessions" in content, "Legacy session endpoints should still exist"

    def test_imports_json_response(self):
        content = BUILDER_PATH.read_text()
        assert "JSONResponse" in content, "Must import JSONResponse for deprecation headers"

    def test_at_least_25_routes(self):
        content = BUILDER_PATH.read_text()
        count = content.count("@router.")
        assert count >= 25, f"Expected at least 25 route decorators, found {count}"
