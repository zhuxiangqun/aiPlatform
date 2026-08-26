"""Static tests for L5 release wiring (plan-app-factory-l5)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUILDER_ROUTER = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"
BUILDER_SERVICE = ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py"
def _service_sources() -> str:
    """P1-14 God Class 拆分：BuilderProjectService 方法分布在主类 + L2L5/Deploy Mixin
    （方法经 MRO 可达），静态断言拼接三文件。"""
    _root = ROOT / "aiPlat-platform" / "builder"
    return (
        (_root / "builder_project_service.py").read_text()
        + "\n" + (_root / "builder_l2l5_mixin.py").read_text()
        + "\n" + (_root / "builder_deploy_mixin.py").read_text()
    )

RELEASE_ENGINE = ROOT / "aiPlat-platform" / "builder" / "release_engine.py"


class TestL5Endpoints:
    def test_release_endpoints(self):
        content = BUILDER_ROUTER.read_text()
        for path in ("/release", "/releases", "releases/{version}/canary",
                     "releases/{version}/full", "releases/{version}/rollback"):
            assert path in content, f"missing {path}"


class TestL5Service:
    def test_methods(self):
        content = _service_sources()
        for m in ("async def create_release", "async def list_releases",
                  "async def set_release_status", "async def _infra_deploy_service"):
            assert m in content, f"missing {m}"

    def test_release_engine_caller(self):
        content = _service_sources()
        assert "from builder.release_engine import" in content

    def test_migration_gate(self):
        content = _service_sources()
        assert "pending_migrations" in content
        assert "请先应用再发布" in content

    def test_infra_opt_in(self):
        content = _service_sources()
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


class TestL5V2Facade:
    """L5 v2: infra deploy via CoreFacade (no platform→infra direct import)."""

    def test_facade_exposes_deploy(self):
        content = (ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py").read_text()
        assert "def deploy_app_service" in content

    def test_bridge_has_deploy(self):
        content = (ROOT / "aiPlat-core" / "core" / "harness" / "infrastructure" / "infra_bridge.py").read_text()
        assert "def deploy_app_service" in content

    def test_platform_uses_facade_not_infra(self):
        content = _service_sources()
        assert "from core.api.core_facade import deploy_app_service" in content
        assert "from infra" not in content  # no direct infra import

    def test_canary_weight_field(self):
        content = RELEASE_ENGINE.read_text()
        assert "canary_weight" in content

    def test_canary_endpoint_weight(self):
        content = BUILDER_ROUTER.read_text()
        assert "canary_weight" in content
