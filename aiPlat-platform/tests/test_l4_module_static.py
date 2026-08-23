"""Static tests for L4 multi-module wiring (plan-app-factory-l4).

Verifies: module endpoints, service methods, module_id routing, cross_module
having production callers, and L2/L3 reuse paths.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUILDER_ROUTER = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"
BUILDER_SERVICE = ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py"
CROSS_MODULE = ROOT / "aiPlat-platform" / "builder" / "cross_module.py"


class TestL4Endpoints:
    def test_module_endpoints(self):
        content = BUILDER_ROUTER.read_text()
        for path in ("/projects/{project_id}/modules", "/cross-module-impact",
                     "/module-orchestrate", "modules/{module_id:path}/import-repo"):
            assert path in content, f"missing {path}"


class TestL4Service:
    def test_module_methods(self):
        content = BUILDER_SERVICE.read_text()
        for m in ("async def create_modules", "async def list_modules",
                  "async def cross_module_impact", "async def module_orchestrate",
                  "def _module_root", "def _module_repo", "def _module_roots"):
            assert m in content, f"missing {m}"

    def test_import_repo_module_id(self):
        content = BUILDER_SERVICE.read_text()
        assert "module_id: str = \"default\"" in content
        assert "proj.setdefault(\"module_repos\", {})" in content

    def test_rebuild_module_param(self):
        content = BUILDER_SERVICE.read_text()
        assert "module_id: str = \"default\"" in content
        assert "self._module_repo(project_id, module_id)" in content

    def test_cross_module_caller(self):
        content = BUILDER_SERVICE.read_text()
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
        content = BUILDER_SERVICE.read_text()
        assert "default" in content  # implicit single-module semantics
