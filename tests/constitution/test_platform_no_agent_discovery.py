"""
Architecture Constitution Tests: Platform No Agent Discovery Logic

Enforces boundary-standard.md §决策树: Agent discovery (scanning agent directories,
building catalogs, recommending teams) is a general AI capability that belongs in Core.

Platform must NOT implement:
- Agent catalog scanning (glob over agent directories)
- Agent frontmatter aggregation (building catalogs from AGENT.md)
- LLM-based team recommendation (model inference for team planning)

These belong in Core per boundary-standard.md.
"""

import ast
from pathlib import Path
from typing import Dict, List, Set

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_BUILDER = WORKSPACE_ROOT / "aiPlat-platform" / "builder"

KNOWN_DEBT: Dict[str, str] = {
    "builder_roles.py": (
        "_load_agent_md and _role_agent_md_path "
        "to be moved to core agent frontmatter loader"
    ),
}


def _module_functions(fp: Path) -> List[str]:
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    funcs: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node.name)
    return funcs


def _module_staticmethods(fp: Path) -> List[str]:
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    methods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in getattr(node, "decorator_list", []):
                if isinstance(dec, ast.Name) and dec.id == "staticmethod":
                    methods.append(node.name)
    return methods


def _relative_path(fp: Path) -> str:
    try:
        return str(fp.relative_to(PLATFORM_BUILDER))
    except ValueError:
        return str(fp)


def test_platform_no_agent_discovery():
    """Platform builder/ must not implement agent catalog/discovery logic."""
    violations: List[str] = []

    for fp in PLATFORM_BUILDER.rglob("*.py"):
        if not fp.is_file() or "__pycache__" in str(fp):
            continue
        rel = _relative_path(fp)
        if rel in KNOWN_DEBT:
            continue
        funcs = _module_functions(fp) + _module_staticmethods(fp)
        for fname in funcs:
            if any(kw in fname.lower() for kw in [
                "build_agent_catalog", "list_available_agents",
                "recommend_team_stages", "scan_agents",
                "agent_discovery", "agent_catalog",
            ]):
                violations.append(f"{rel}::{fname}()")

    assert not violations, (
        f"Platform builder/ has {len(violations)} agent discovery function(s):\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nAgent discovery and team recommendation are general AI capabilities. "
        "They belong in Core per boundary-standard.md §决策树."
    )


def test_platform_no_direct_agent_fs_scan():
    """Platform must not directly scan agent filesystem directories."""
    violations: List[str] = []

    for fp in PLATFORM_BUILDER.rglob("*.py"):
        if not fp.is_file() or "__pycache__" in str(fp):
            continue
        rel = _relative_path(fp)
        if rel in KNOWN_DEBT:
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Check for raw filesystem agent directory scanning
        if "glob.glob" in content and "agents" in content and "AGENT.md" in content:
            violations.append(f"{rel}: agent filesystem scan")

    assert not violations, (
        f"Platform builder/ has {len(violations)} agent filesystem scan(s):\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nAgent filesystem scanning belongs in Core per boundary-standard.md §决策树."
    )
