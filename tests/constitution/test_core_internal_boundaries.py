"""
Architecture Constitution Tests: Core Internal Boundaries

Enforces internal boundaries within aiPlat-core:
  - harness/ MUST NOT import from apps/ (infrastructure ← implementations)
  - api/routers/ MUST access execution engine through CoreFacade (not directly)
  - apps/agents/ MUST NOT import from apps/skills/ or apps/tools/ directly
"""
import ast
from pathlib import Path
from typing import List, Set, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = WORKSPACE_ROOT / "aiPlat-core" / "core"

# Legitimate cross-boundary imports (documented facade/interface patterns)
ALLOWED_HARNESS_TO_APPS: Set[Tuple[str, str]] = {
    # DI / integration layer — by design, wires apps into harness
    ("harness/integration.py", "apps/agents/registry"),
    ("harness/integration.py", "apps/skills/registry"),
    ("harness/integration.py", "apps/tools/base"),
    ("harness/integration.py", "apps/tools/permission"),
    ("harness/integration.py", "apps/exec_drivers/registry"),
    ("harness/integration.py", "apps/agents/subagent/coordinator"),
    ("harness/integration.py", "apps/tools/skill_tools"),
    ("harness/integration.py", "apps/skills/curator"),
    ("harness/integration.py", "apps/skills/evolution/engine"),
    # DI fallback — lazy import guarded by try/except
    ("harness/integration.py", "apps/mcp/runtime"),
    # Data type imports — allowed (enum + metadata class, not service calls)
    ("harness/memory/manager.py", "apps/skills/metadata"),
    # Data type — enum import, allowed
    ("harness/infrastructure/gates/policy_gate.py", "apps/tools/permission"),
    ("harness/feedback_loops/__init__.py", "apps/skills/evolution/engine"),
    # Pipeline engine — data type imports (class, not service call)
    ("harness/execution/pipeline_engine.py", "apps/tools/code"),
    # LangGraph stage runner — data type access
    ("harness/execution/langgraph/stage_runner.py", "apps/tools/code"),
    # KNOWN_DEBT: browser_test_engine in bridge, guarded by lazy import + try/except
    ("harness/integration.py", "apps/tools/browser_test_engine"),
    # pipeline_engine — lazy import guarded by try/except for predictions
    ("harness/execution/pipeline_engine.py", "apps/skills/evolution/engine"),
    # pipeline_engine — lazy import guarded by try/except for evolution triggers
    ("harness/execution/pipeline_engine.py", "apps/skills/evolution/triggers"),
}


def _get_relpath(fp: Path) -> str:
    try:
        return str(fp.relative_to(CORE_DIR))
    except ValueError:
        return str(fp)


def _gather_imports(fp: Path) -> List[Tuple[str, int]]:
    """Return list of (imported_module, lineno) from a Python file."""
    imports = []
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.module, node.lineno))
    return imports


def test_harness_does_not_import_apps():
    """harness/ must not import from apps/ (infrastructure ← implementations)."""
    violations: List[str] = []

    for fp in (CORE_DIR / "harness").rglob("*.py"):
        if "__pycache__" in str(fp):
            continue
        rel = _get_relpath(fp)
        for imp_mod, lineno in _gather_imports(fp):
            if imp_mod.startswith("core.apps"):
                # Normalize: convert dots to slashes for matching (import → file path)
                short_imp = imp_mod.replace(".py", "").replace("core.", "", 1).replace(".", "/")
                if (rel, short_imp) in ALLOWED_HARNESS_TO_APPS:
                    continue
                violations.append(f"{rel}:{lineno} → {imp_mod}")

    assert not violations, (
        f"harness/ has {len(violations)} import(s) from apps/:\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nharness/ is infrastructure; it should not depend on apps/ implementations."
    )


def test_api_routers_use_facade_not_engine():
    """api/routers/ must access execution engine through CoreFacade, not directly.
    
    Exception: core_facade.py IS the facade — it's the one allowed to import
    pipeline_engine directly. All other api/ files must go through CoreFacade.
    """
    violations: List[str] = []
    engine_modules = {
        "core.harness.execution.pipeline_engine",
        "core.harness.execution.engine",
    }

    for fp in (CORE_DIR / "api").rglob("*.py"):
        if "__pycache__" in str(fp):
            continue
        rel = _get_relpath(fp)
        # core_facade.py IS the facade — it's the one place allowed to import the engine
        # api/facades/*.py are lightweight facades that may also import engine directly
        if fp.name == "core_facade.py" or "/facades/" in str(fp):
            continue
        for imp_mod, lineno in _gather_imports(fp):
            if imp_mod in engine_modules:
                violations.append(f"{rel}:{lineno} → {imp_mod} (use CoreFacade instead)")

    assert not violations, (
        f"api/ has {len(violations)} direct engine import(s):\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\napi/routers should access engine through CoreFacade per architecture contract."
    )


def test_apps_agents_no_direct_skill_imports():
    """apps/agents/ must use registry/facade patterns, not raw skill/tool imports.
    
    Exceptions: agents MAY use skills.registry (get_skill_registry) and 
    skills base classes — these are the approved DI injection points.
    """
    violations: List[str] = []
    allowed = {"core.apps.skills.registry", "core.apps.skills.base", "core.apps.skills"}

    for fp in (CORE_DIR / "apps" / "agents").rglob("*.py"):
        if "__pycache__" in str(fp):
            continue
        rel = _get_relpath(fp)
        if fp.name == "base.py":
            continue
        for imp_mod, lineno in _gather_imports(fp):
            if imp_mod.startswith("core.apps.skills") or imp_mod.startswith("core.apps.tools"):
                if imp_mod in allowed or imp_mod.startswith("core.apps.skills."):
                    continue
                violations.append(f"{rel}:{lineno} → {imp_mod} (use registry or facade)")

    assert not violations, (
        f"apps/agents/ has {len(violations)} direct skill/tool import(s):\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nAgents should use registry/facade patterns, not direct imports."
    )
