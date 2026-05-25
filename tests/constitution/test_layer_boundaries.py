"""
Architecture Constitution Tests: Layer Boundaries

Enforces the strict one-way dependency chain:
    app -> platform -> core -> infra

Each test checks that:
1. A layer does NOT import from layers it's forbidden to depend on
2. A layer does NOT directly instantiate classes it should access via facade
3. A layer does NOT contain code that belongs in another layer

These tests MUST pass on every PR. Failure = architecture violation, merge blocked.

Design authority: docs/index.md, docs/architecture/system-architecture-contract.md
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# workspace root is the parent of this test file's great-grandparent:
# tests/constitution/test_layer_boundaries.py -> ../../ -> workspace root
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _has_transitional_marker(fp: Path) -> bool:
    """Check if a file has an approved transitional marker (DEPRECATED comment
    with clear migration plan, or feature flag guard with documented path)."""
    try:
        text = fp.read_text(encoding="utf-8", errors="ignore")[:4096]
    except Exception:
        return False
    markers = [
        r'DEPRECATED:.*migrate\s+to\s+',
        r'# NOTE:.*should move to.*layer',
    ]
    for m in markers:
        if re.search(m, text, re.IGNORECASE):
            return True
    return False

# ============================================================================
# Helpers
# ============================================================================


def _find_py_files(dir_path: Path) -> List[Path]:
    """Return all .py files under dir_path, excluding __pycache__ and tests/."""
    files = []
    for root, dirs, filenames in os.walk(str(dir_path)):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", "node_modules", ".git")]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(root) / f)
    return files


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _grep_files(files: List[Path], pattern: str) -> List[Tuple[Path, int, str]]:
    """Search files for a regex pattern. Returns (path, lineno, line_content)."""
    hits = []
    compiled = re.compile(pattern)
    for fp in files:
        try:
            for i, line in enumerate(_read_file(fp).split("\n"), 1):
                if compiled.search(line):
                    hits.append((fp, i, line.strip()))
        except Exception:
            pass
    return hits


def _grep_imports(files: List[Path], module_pattern: str) -> List[Tuple[Path, int, str]]:
    """Search for Python import statements matching module_pattern."""
    pattern = rf'(?:from\s+{module_pattern}\s+import|import\s+{module_pattern})'
    return _grep_files(files, pattern)


def _grep_code(files: List[Path], pattern: str) -> List[Tuple[Path, int, str]]:
    """Search files for a code pattern (non-import)."""
    return _grep_files(files, pattern)


def _production_files(layer_dir: str, exclude_dirs: List[str] = None) -> List[Path]:
    """Find production .py files, excluding tests/ and generated/."""
    exclude = {"__pycache__", ".pytest_cache", "tests", "generated"}
    if exclude_dirs:
        exclude.update(exclude_dirs)
    dir_path = WORKSPACE_ROOT / layer_dir
    if not dir_path.exists():
        return []
    files = []
    for root, dirs, filenames in os.walk(str(dir_path)):
        dirs[:] = [d for d in dirs if d not in exclude]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(root) / f)
    return files


# ============================================================================
# Tests: Import Direction
# ============================================================================


class TestAppDoesNotImportCoreOrInfra:
    """aiPlat-app MUST NOT import from aiPlat-core or aiPlat-infra."""

    def test_app_does_not_import_core(self):
        files = _production_files("aiPlat-app")
        hits = _grep_imports(files, r"core\.")
        # Exclude generated/ — those are pipeline output artifacts, not app source
        hits = [(p, l, s) for p, l, s in hits if "generated" not in str(p)]
        assert not hits, (
            f"aiPlat-app MUST NOT import from core. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_app_does_not_import_infra(self):
        files = _production_files("aiPlat-app")
        hits = _grep_imports(files, r"infra\.")
        hits = [(p, l, s) for p, l, s in hits if "generated" not in str(p)]
        assert not hits, (
            f"aiPlat-app MUST NOT import from infra. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_app_does_not_run_its_own_api_server(self):
        """App MUST NOT run its own FastAPI/Flask server — it's not an API layer.
        Transitional: management console proxy endpoints marked DEPRECATED are allowed."""
        files = _production_files("aiPlat-app")
        # Check for uvicorn.run / app.run in production files (not generated/)
        pattern = r"(uvicorn\.run|flask.*run|FastAPI\(|app\s*=\s*FastAPI)"
        hits = _grep_code(files, pattern)
        hits = [(p, l, s) for p, l, s in hits
                if "generated" not in str(p)
                and "conftest" not in str(p).lower()
                and not _has_transitional_marker(p)]
        assert not hits, (
            f"aiPlat-app MUST NOT run its own API server. Found:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_app_does_not_access_database_directly(self):
        """App MUST NOT access databases directly — should go through platform API."""
        files = _production_files("aiPlat-app")
        pattern = r"(sqlite3\.connect|create_engine\(|aiosqlite)"
        hits = _grep_code(files, pattern)
        hits = [(p, l, s) for p, l, s in hits
                if "generated" not in str(p)
                and "conftest" not in str(p).lower()
                and not _has_transitional_marker(p)]
        assert not hits, (
            f"aiPlat-app MUST NOT access database directly. Found:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )


class TestPlatformDoesNotImportInfra:
    """aiPlat-platform MUST NOT import from aiPlat-infra."""

    def test_platform_does_not_import_infra(self):
        files = _production_files("aiPlat-platform")
        hits = _grep_imports(files, r"infra\.")
        assert not hits, (
            f"aiPlat-platform MUST NOT import from infra. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_platform_does_not_directly_instantiate_pipeline_engine(self):
        """Platform MUST use CoreFacade, not PipelineEngine() directly."""
        files = _production_files("aiPlat-platform")
        # Detect PipelineEngine( — being called as constructor
        pattern = r"PipelineEngine\("
        hits = _grep_code(files, pattern)
        # Allow type annotations (PipelineEngine as type hint) — only flag constructor calls
        actual_violations = []
        for p, l, s in hits:
            # If it's just a type hint (e.g., "Dict[str, PipelineEngine]"), skip
            if re.match(r'.*:\s*(Dict|List|Optional|Union)\[.*PipelineEngine.*\]\s*=', s):
                continue
            actual_violations.append((p, l, s))
        assert not actual_violations, (
            f"aiPlat-platform MUST NOT directly instantiate PipelineEngine(). "
            f"Use CoreFacade.create_pipeline_engine() instead. Found {len(actual_violations)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in actual_violations)
        )

    def test_platform_does_not_contain_pipeline_execution_logic(self):
        """Platform MUST NOT execute pipeline stages directly — only Core does that."""
        files = _production_files("aiPlat-platform")
        # Check for direct methods that bypass CoreFacade
        patterns = [
            (r"engine\.initialize\(", "engine.initialize() — must go through CoreFacade"),
            (r"engine\.approve\(", "engine.approve() — must go through CoreFacade"),
            (r"engine\.reject\(", "engine.reject() — must go through CoreFacade"),
            (r"engine\.rollback\(", "engine.rollback() — must go through CoreFacade"),
            (r"engine\.resume_from\(", "engine.resume_from() — must go through CoreFacade"),
        ]
        all_violations = []
        for pattern, desc in patterns:
            hits = _grep_code(files, pattern)
            for p, l, s in hits:
                all_violations.append((p, l, s, desc))
        assert not all_violations, (
            f"aiPlat-platform MUST NOT execute pipeline directly. Use CoreFacade. "
            f"Found {len(all_violations)} violations:\n"
            + "\n".join(f"  {p}:{l}: [{d}] {s}" for p, l, s, d in all_violations)
        )


class TestCoreDoesNotImportPlatformOrApp:
    """aiPlat-core MUST NOT import from aiPlat-platform or aiPlat-app."""

    def test_core_does_not_import_platform(self):
        files = _production_files("aiPlat-core")
        hits = _grep_imports(files, r"platform\.")
        assert not hits, (
            f"aiPlat-core MUST NOT import from platform. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_core_does_not_import_app(self):
        files = _production_files("aiPlat-core")
        hits = _grep_imports(files, r"app\.")
        assert not hits, (
            f"aiPlat-core MUST NOT import from app. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )


class TestInfraDoesNotImportInternal:
    """aiPlat-infra MUST NOT import from any internal layer."""

    def test_infra_does_not_import_core(self):
        files = _production_files("aiPlat-infra")
        hits = _grep_imports(files, r"core\.")
        assert not hits, (
            f"aiPlat-infra MUST NOT import from core. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_infra_does_not_import_platform(self):
        files = _production_files("aiPlat-infra")
        hits = _grep_imports(files, r"platform\.")
        assert not hits, (
            f"aiPlat-infra MUST NOT import from platform. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_infra_does_not_import_app(self):
        files = _production_files("aiPlat-infra")
        hits = _grep_imports(files, r"app\.")
        assert not hits, (
            f"aiPlat-infra MUST NOT import from app. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )

    def test_infra_does_not_import_management(self):
        files = _production_files("aiPlat-infra")
        hits = _grep_imports(files, r"management\.")
        # Allow self-imports (infra.management.* within infra itself)
        hits = [(p, l, s) for p, l, s in hits if "aiPlat-management" in str(p) or "infra/management" not in str(p)]
        assert not hits, (
            f"aiPlat-infra MUST NOT import from aiPlat-management. Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )


# ============================================================================
# Tests: Facade Usage
# ============================================================================


class TestCoreFacadeIsUsed:
    """Platform MUST use CoreFacade as the sole entry point to core."""

    def test_core_facade_exists(self):
        facade_path = WORKSPACE_ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
        assert facade_path.exists(), "CoreFacade file missing at aiPlat-core/core/api/core_facade.py"

    def test_platform_uses_core_facade_for_engine_access(self):
        """Platform must import PipelineEngine through CoreFacade, not directly."""
        files = _production_files("aiPlat-platform")
        # Direct import of PipelineEngine from core.harness.execution
        pattern = r"from\s+core\.harness\.execution\.pipeline_engine\s+import"
        hits = _grep_code(files, pattern)
        assert not hits, (
            f"aiPlat-platform MUST import PipelineEngine via CoreFacade, not directly. "
            f"Found {len(hits)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in hits)
        )


# ============================================================================
# Tests: Missing dependency declarations
# ============================================================================


class TestDependencyDeclarations:
    """Each layer MUST declare its dependencies in pyproject.toml or equivalent."""

    def test_core_declares_infra_dependency(self):
        """Core's pyproject.toml must list aiplat-infra as dependency."""
        pyproject = WORKSPACE_ROOT / "aiPlat-core" / "pyproject.toml"
        if not pyproject.exists():
            return  # Skip — not a buildable package
        content = pyproject.read_text()
        assert "aiplat-infra" in content, (
            "aiPlat-core/pyproject.toml must declare aiplat-infra as a dependency"
        )

    def test_platform_has_dependency_declaration(self):
        """Platform must have a pyproject.toml or requirements.txt declaring core dependency."""
        pyproject = WORKSPACE_ROOT / "aiPlat-platform" / "pyproject.toml"
        setup_py = WORKSPACE_ROOT / "aiPlat-platform" / "setup.py"
        requirements = WORKSPACE_ROOT / "aiPlat-platform" / "requirements.txt"
        has_decl = pyproject.exists() or setup_py.exists() or requirements.exists()
        assert has_decl, (
            "aiPlat-platform must have pyproject.toml, setup.py, or requirements.txt "
            "declaring its dependency on aiplat-core"
        )

    def test_app_has_dependency_declaration(self):
        """App must have a pyproject.toml or requirements.txt declaring platform dependency."""
        pyproject = WORKSPACE_ROOT / "aiPlat-app" / "pyproject.toml"
        setup_py = WORKSPACE_ROOT / "aiPlat-app" / "setup.py"
        requirements = WORKSPACE_ROOT / "aiPlat-app" / "requirements.txt"
        has_decl = pyproject.exists() or setup_py.exists() or requirements.exists()
        assert has_decl, (
            "aiPlat-app must have pyproject.toml, setup.py, or requirements.txt "
            "declaring its dependency on aiplat-platform"
        )


# ============================================================================
# Tests: Router Boundary — Core must not define platform-layer routes
# ============================================================================


class TestCoreHasNoPlatformRoutes:
    """Core MUST NOT define HTTP routes that belong to the platform layer."""

    FORBIDDEN_ROUTES = {
        "approvals",       # Approval workflows → platform
        "tenant_policies", # Tenant policy management → platform
        "quota",           # Quota/billing → platform
        "permissions",     # User permissions → platform
        "onboarding",      # Tenant onboarding → platform
        "gateway",         # API gateway → platform
        "gate_policies",   # Gate policy management → platform
        "change_control",  # Change control → platform
        "chat",            # Web chat → app layer
        "channel_adapters", # Channel adaptation → app layer
        "conversations",   # Conversation sessions → app/platform
        "policy",          # Policy snapshots → platform
        "ops_exports",     # Ops exports → platform
    }

    def test_core_routers_dont_overlap_platform(self):
        routers_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "api" / "routers"
        if not routers_dir.exists():
            return
        existing = set()
        for f in routers_dir.iterdir():
            if f.suffix == ".py" and f.stem != "__init__":
                existing.add(f.stem)
        overlap = existing & self.FORBIDDEN_ROUTES
        # Exempt routes with approved transitional markers (DEPRECATED + migration plan)
        actual_violations = set()
        for route_name in overlap:
            route_file = routers_dir / f"{route_name}.py"
            if not _has_transitional_marker(route_file):
                actual_violations.add(route_name)
        assert not actual_violations, (
            f"Core MUST NOT define these platform/app routes: {actual_violations}. "
            f"Routes marked as DEPRECATED with migration plan are allowed as transitional debt. "
            f"These belong in aiPlat-platform/ or aiPlat-app/."
        )
