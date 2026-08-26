"""Static tests for L4.5 migration wiring (plan-app-factory-l45)."""
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

SCHEMA_MIGRATION = ROOT / "aiPlat-platform" / "builder" / "schema_migration.py"


class TestL45Endpoints:
    def test_migration_endpoints(self):
        content = BUILDER_ROUTER.read_text()
        for path in ("migration-preview", "/migrations", "migrations/apply",
                     "migrations/{migration_id}/rollback"):
            assert path in content, f"missing {path}"


class TestL45Service:
    def test_methods(self):
        content = _service_sources()
        for m in ("async def migration_preview", "async def list_migrations",
                  "async def apply_migration", "async def rollback_migration",
                  "def _check_cross_module_fields", "def _module_code_files"):
            assert m in content, f"missing {m}"

    def test_schema_migration_caller(self):
        content = _service_sources()
        assert "from builder.schema_migration import" in content

    def test_destructive_confirmation(self):
        content = _service_sources()
        assert "destructive_migration_requires_confirmation" in content
        assert "显式确认" in content


class TestL45Module:
    def test_core_functions(self):
        content = SCHEMA_MIGRATION.read_text()
        for fn in ("def extract_schema", "def diff_schema", "def generate_migration"):
            assert fn in content, f"missing {fn}"

    def test_up_down_paired(self):
        content = SCHEMA_MIGRATION.read_text()
        assert "up_sql" in content and "down_sql" in content
