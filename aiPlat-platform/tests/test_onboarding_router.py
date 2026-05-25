"""Tests for onboarding.py router — onboarding API static analysis."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONBOARDING_PATH = ROOT / "aiPlat-platform" / "api" / "routers" / "onboarding.py"


class TestOnboardingStatic:
    def test_file_exists(self):
        assert ONBOARDING_PATH.exists()

    def test_has_core_endpoints(self):
        content = ONBOARDING_PATH.read_text()
        assert "/onboarding/state" in content
        assert "/onboarding/default-llm" in content
        assert "/onboarding/secrets/status" in content

    def test_has_tenant_endpoints(self):
        content = ONBOARDING_PATH.read_text()
        assert "/onboarding/init-tenant" in content
        assert "/onboarding/evidence/runs" in content

    def test_uses_platform_store_for_tenants(self):
        content = ONBOARDING_PATH.read_text()
        assert "platform_store" in content, "Must use platform_store for tenant operations"

    def test_uses_core_facade_not_deep_harness(self):
        content = ONBOARDING_PATH.read_text()
        # Must use CoreFacade for crypto, not deep harness imports
        assert "core.api.core_facade" in content

    def test_no_deprecated_crypto_imports(self):
        content = ONBOARDING_PATH.read_text()
        # Must NOT import from crypto/__init__, crypto/signature, crypto/secretbox directly
        assert "infrastructure.crypto.signature" not in content
        assert "infrastructure.crypto.secretbox" not in content

    def test_has_environment_secrets_operation(self):
        tree = ast.parse(ONBOARDING_PATH.read_text())
        methods = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and not node.name.startswith("_")]
        assert "get_secrets_status" in methods
        assert "migrate_secrets" in methods

    def test_has_at_least_10_endpoints(self):
        content = ONBOARDING_PATH.read_text()
        count = content.count("@router.")
        assert count >= 10, f"Expected at least 10 routes, found {count}"
