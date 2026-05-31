"""
Hot-reload wiring — registers FileWatcher callbacks for cache invalidation.

Called at server startup to enable hot-reload of code graphs and skill deps.
"""

from __future__ import annotations

import os
from pathlib import Path


def wire_hot_reload():
    u"""Register callbacks on the infra FileWatcher for hot-reload."""
    try:
        from infra.management.file_watcher import get_file_watcher
        watcher = get_file_watcher()
    except (ImportError, ModuleNotFoundError):
        return  # infra not available (e.g., testing)

    # Watch paths from env var
    watch_paths = os.getenv("AIPLAT_CONFIG_WATCH_PATHS", "")
    if not watch_paths:
        # Default: watch skill and agent dirs
        from core import __file__ as core_init
        core_dir = Path(core_init).parent
        skill_dir = core_dir / "engine" / "skills"
        agent_dir = core_dir / "engine" / "agents"
        project_root = os.getenv("AIPLAT_PROJECT_ROOT", os.getcwd())
        code_dirs = [
            os.path.join(project_root, "aiPlat-core"),
            os.path.join(project_root, "aiPlat-management/frontend/src"),
        ]
        for d in code_dirs:
            if os.path.isdir(d):
                watch_paths += f"{d},"

    paths = [p.strip() for p in watch_paths.split(",") if p.strip() and os.path.exists(p.strip())]

    for p in paths:
        def _on_file_change(filepath):
            import logging
            logger = logging.getLogger("hot_reload")
            logger.info(f"file changed: {filepath}")
            if filepath.endswith(('.py', '.ts', '.tsx', '.md', '.yaml', '.yml')):
                try:
                    from core.harness.knowledge.code_graph import clear_cache
                    clear_cache()
                except Exception:
                    pass
                try:
                    from core.harness.knowledge.capability_graph import clear_capability_cache
                    clear_capability_cache()
                except Exception:
                    pass
        watcher.watch(p, _on_file_change)

    watcher.start()
