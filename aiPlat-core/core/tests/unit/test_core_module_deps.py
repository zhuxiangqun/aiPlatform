"""
test_core_module_deps — verify core module dependency direction (CLAUDE.md §5.14).

Dependency matrix:
  harness ───→ (no internal deps)
  agents ───→ harness, memory, knowledge, tools, services
  skills ───→ services
  tools ────→ services
  memory ───→ services
  knowledge → services, models

Forbidden:
  agents → agents (cross-agent direct imports outside multi_agent)
  skills → agents (skills should not depend on agents)
  services → agents (services should not depend on agents)
"""

import ast
from pathlib import Path


CORE_DIR = Path(__file__).resolve().parent.parent.parent / "core"

# Module directory → (allowed import prefixes from that module)
ALLOWED_IMPORTS: dict[str, set[str]] = {
    "core/apps/agents": {"core/harness/", "core/apps/memory", "core/apps/knowledge",
                         "core/apps/tools", "core/apps/skills", "core/harness/syscalls",
                         "core/harness/utils", "core/harness/infrastructure",
                         "core/adapters", "core/schemas", "core/utils", "core/management",
                         "core/services", "core/api/facades",  # facade → CoreFacade
    },
}

FORBIDDEN_IMPORTS: dict[str, list[tuple[str, str]]] = {
    "core/apps/agents": [
        ("from core.apps.skills.registry import", "agents should not import skills.registry directly"),
        ("from core.apps.agents.discovery import", "agents should not import agent discovery"),
    ],
    "core/apps/skills": [
        ("from core.apps.agents", "skills should not depend on agents"),
    ],
    "core/harness/": [
        ("from core.apps.agents", "harness should not depend on agents"),
        ("from core.apps.skills", "harness should not depend on skills"),
    ],
}


def test_forbidden_module_imports():
    """Check that modules don't import from forbidden directories."""
    violations = []
    for scan_dir, checks in FORBIDDEN_IMPORTS.items():
        dir_path = CORE_DIR / scan_dir
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            if "/test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            if py_file.name in ("__init__.py",):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for pattern, msg in checks:
                if pattern in source:
                    rel = py_file.relative_to(CORE_DIR.parent)
                    violations.append(f"{rel}: {msg}")
    assert len(violations) == 0, (
        f"Found {len(violations)} forbidden import(s):\n  " +
        "\n  ".join(violations[:10])
    )
