"""Static tests for L4 multi-module wiring (plan-app-factory-l4).

Verifies: module endpoints, service methods, module_id routing, cross_module
having production callers, and L2/L3 reuse paths.
"""
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

CROSS_MODULE = ROOT / "aiPlat-platform" / "builder" / "cross_module.py"


class TestL4Endpoints:
    def test_module_endpoints(self):
        content = BUILDER_ROUTER.read_text()
        for path in ("/projects/{project_id}/modules", "/cross-module-impact",
                     "/module-orchestrate", "modules/{module_id:path}/import-repo"):
            assert path in content, f"missing {path}"


class TestL4Service:
    def test_module_methods(self):
        content = _service_sources()
        for m in ("async def create_modules", "async def list_modules",
                  "async def cross_module_impact", "async def module_orchestrate",
                  "def _module_root", "def _module_repo", "def _module_roots"):
            assert m in content, f"missing {m}"

    def test_import_repo_module_id(self):
        content = _service_sources()
        assert "module_id: str = \"default\"" in content
        assert "proj.setdefault(\"module_repos\", {})" in content

    def test_rebuild_module_param(self):
        content = _service_sources()
        assert "module_id: str = \"default\"" in content
        assert "self._module_repo(project_id, module_id)" in content

    def test_cross_module_caller(self):
        content = _service_sources()
        assert "from builder.cross_module import" in content
        assert "impact_closure" in content
        assert "topological_order" in content


class TestL4CrossModuleModule:
    def test_core_functions(self):
        content = CROSS_MODULE.read_text()
        for fn in ("def scan_module_contracts", "def analyze_cross_module",
                   "def impact_closure", "def topological_order"):
            assert fn in content, f"missing {fn}"

    def test_contract_kinds(self):
        content = CROSS_MODULE.read_text()
        assert "apis" in content and "events" in content and "entities" in content

    def test_single_module_compat_note(self):
        content = _service_sources()
        assert "default" in content  # implicit single-module semantics
