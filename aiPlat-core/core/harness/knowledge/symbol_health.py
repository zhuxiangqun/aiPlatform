"""
Shared symbol-health utilities for code-graph dead-code detection.

Used by: overview.py, diagnostics.py (single source of truth).
"""

from typing import Dict, Any, List, Tuple


def is_excluded_from_dead_code(nid: str) -> bool:
    """
    Check if a code-graph node should be excluded from dead-code detection.

    Returns True if the file is legitimately excluded (dynamic dispatch,
    DI, registry-loaded, entry point, generated, etc.), meaning it should
    NOT be counted as dead code.
    """
    # 1. Prefix match (frontend app files)
    _EXCLUDED_PREFIXES = ('aiPlat-app/', 'aiplat-app/')
    if any(nid.startswith(p) for p in _EXCLUDED_PREFIXES):
        return True

    # 2. Subdirectory match (broad exclusions)
    _EXCLUDED_DIRS = (
        'tests/', '/test_', '/generated/', '/engine/agents/', '/engine/skills/',
        '/infrastructure/gates/', '/scripts/', '/arch_guard_rules/', '/lint_rules/',
        '/core/api/routers/', '/core/apps/tools/', '/core/tools/',
        '/core/harness/execution/langgraph/', '/core/adapters/llm/',
        '/core/harness/syscalls/', '/workspace_seeds/',
        '/kb/poc/', '/kb/intelligence/',
        '/infra/utils/', '/infra/management/model/',
        '/harness/health/', '/knowledge/health_rules/',
    )
    if any(p in nid for p in _EXCLUDED_DIRS):
        return True

    # 3. Suffix match (specific files and extensions)
    _EXCLUDED_SUFFIXES = (
        'server.py', 'main.py', '__init__.py', '.sh', '.cfg', '.tsx', '.ts', '.jsx',
        '/execution/conditional.py', '/vector/utils.py',
        'core/schemas_tools.py', 'core/schemas.py',
        '/knowledge/reranker.py', 'infra/management/config.py',
        '/auth/rbac.py', 'management/run.py', 'management/capability_convergence.py',
        '/health/collector.py', '/health/registry.py',
        # Wired modules called via import chains (caller_verify false positives)
        '/knowledge/wiki_health_rules.py',
    )
    if any(nid.endswith(s) for s in _EXCLUDED_SUFFIXES):
        return True

    # 4. Agent/skill dirs — exclude leaf files but keep __init__.py (registry connector)
    if ('/apps/agents/' in nid or '/apps/skills/' in nid) and not nid.endswith('/__init__.py'):
        return True

    # 5. Builder files — exclude only DI-called/infrastructure files
    if '/builder/' in nid and ('builder_session' in nid or 'builder_roles' in nid):
        return True

    # 6. Specific management tool scripts (loaded dynamically by registries)
    if '/management/' in nid and ('arch_guard_' in nid or 'compliance_checks' in nid or 'skill_linter' in nid):
        return True

    # 7. Management model scanner (dynamically invoked)
    if '/management/model/' in nid and 'scanner' in nid:
        return True

    # 8. Infrastructure adapters (loaded by factory)
    if nid.endswith('_adapter.py') and '/infrastructure/' in nid:
        return True

    # 9. Core utils
    if '/utils/' in nid and 'core/' in nid:
        return True

    # 10. Dashboard adapters (loaded by DI via infra_bridge)
    if '/dashboard/' in nid and nid.endswith('_adapter.py'):
        return True

    # 11. Management API routers (registered via FastAPI include_router)
    if '/management/api/' in nid:
        return True

    return False


def count_dead_code_candidates(nodes: Dict[str, Dict[str, Any]]) -> Tuple[int, List[str]]:
    """
    Count dead-code candidates and return the file list.

    Args:
        nodes: code-graph node dict {node_id: {in, symbols, ...}}

    Returns:
        (count, file_list) — count of dead code candidates and the file paths (up to 50)
    """
    dead_files = [
        nid for nid, n in nodes.items()
        if not is_excluded_from_dead_code(nid)
        and int(n.get('in', 0)) == 0
        and len(n.get('symbols', [])) > 0
    ]
    return len(dead_files), dead_files[:50]
