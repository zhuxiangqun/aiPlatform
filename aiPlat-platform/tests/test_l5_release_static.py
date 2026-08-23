"""Static tests for L5 release wiring (plan-app-factory-l5)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUILDER_ROUTER = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"
BUILDER_SERVICE = ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py"
RELEASE_ENGINE = ROOT / "aiPlat-platform" / "builder" / "release_engine.py"


class TestL5Endpoints:
    def test_release_endpoints(self):
        content = BUILDER_ROUTER.read_text()
        for path in ("/release", "/releases", "releases/{version}/canary",
                     "releases/{version}/full", "releases/{version}/rollback"):
            assert path in content, f"missing {path}"


class TestL5Service:
    def test_methods(self):
        content = BUILDER_SERVICE.read_text()
        for m in ("async def create_release", "async def list_releases",
                  "async def set_release_status", "async def _infra_deploy_service"):
            assert m in content, f"missing {m}"

    def test_release_engine_caller(self):
        content = BUILDER_SERVICE.read_text()
        assert "from builder.release_engine import" in content

    def test_migration_gate(self):
        content = BUILDER_SERVICE.read_text()
        assert "pending_migrations" in content
        assert "请先应用再发布" in content

    def test_infra_opt_in(self):
        content = BUILDER_SERVICE.read_text()
        assert "AIPLAT_L5_INFRA_DEPLOY" in content


class TestL5EngineModule:
    def test_state_machine(self):
        content = RELEASE_ENGINE.read_text()
        for st in ("_READY", "_CANARY", "_FULL", "_ROLLED_BACK"):
            assert st in content, f"missing {st}"
        assert "_VALID_TRANSITIONS" in content

    def test_versioned_artifact(self):
        content = RELEASE_ENGINE.read_text()
        assert "releases" in content and "current" in content
        assert "_write_pointer" in content
