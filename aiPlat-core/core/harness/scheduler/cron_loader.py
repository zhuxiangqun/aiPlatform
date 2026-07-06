"""
cron_loader — startup hook: scan ~/.aiplat/cron/*.yaml and register jobs
with the CronScheduler. Bridges H4 distribution.yaml cron entries into
A2.3 runtime scheduling (kanban task board).
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("aiplat.cron_loader")


def _cron_to_seconds(expr: str) -> int:
    """Minimal cron expression → interval seconds. Supports @hourly/@daily
    and standard 5-field cron. Falls back to 3600."""
    expr = (expr or "").strip()
    if expr == "@hourly" or expr == "0 * * * *":
        return 3600
    if expr == "@daily" or re.match(r"^(\d+) (\d+) \* \* \*$", expr):
        return 86400
    if re.match(r"^\*/?(\d+)", expr):
        try:
            return int(re.match(r"^\*/?(\d+)", expr).group(1)) * 60
        except Exception:
            pass
    return 3600


def load_cron_from_profile(home_dir: str = "") -> int:
    """Scan ~/.aiplat/cron/*.yaml, register each entry with CronScheduler.

    Returns count of registered jobs (0 = no cron entries or all skipped).
    Failure-per-entry isolation: a broken YAML file skips just that entry,
    never blocks the scheduler or the startup sequence.
    """
    h = home_dir or os.path.expanduser(os.environ.get("AIPLAT_HOME", "~/.aiplat"))
    cron_dir = os.path.join(h, "cron")
    if not os.path.isdir(cron_dir):
        logger.debug("cron_loader: no cron directory at %s", cron_dir)
        return 0

    try:
        from core.harness.scheduler.cron import get_cron_scheduler
        from core.harness.coordination.kanban_engine import KanbanEngine
    except Exception as e:
        logger.debug("cron_loader: cannot import scheduler/kanban — skipping (%s)", e)
        return 0

    try:
        import yaml as _yaml
    except ImportError:
        logger.debug("cron_loader: yaml not available — cron registration skipped")
        return 0

    scheduler = get_cron_scheduler()
    kanban = KanbanEngine()
    registered = 0

    for entry_file in sorted(os.listdir(cron_dir)):
        if not entry_file.endswith(".yaml"):
            continue
        fp = os.path.join(cron_dir, entry_file)
        try:
            with open(fp) as f:
                entry = _yaml.safe_load(f)
        except Exception:
            logger.debug("cron_loader: skip unreadable %s", entry_file)
            continue
        if not entry or not isinstance(entry, dict) or "name" not in entry:
            logger.debug("cron_loader: skip malformed entry in %s", entry_file)
            continue

        name = str(entry["name"])
        interval = _cron_to_seconds(entry.get("schedule", ""))
        goal = entry.get("goal", "")
        profile = entry.get("profile", "default")

        async def _handler(goal_name=goal, profile_id=profile):
            try:
                task_id = kanban.create_task(profile_id=profile_id, title=goal_name,
                                             description=f"Cron job '{goal_name}' (scheduler)")
                kanban._transition(task_id, "todo")
                logger.info("cron job '%s': kanban task %s created", goal_name, task_id[:12])
            except Exception as exc:
                logger.warning("cron job '%s' handler failed: %s", goal_name, exc)

        scheduler.register(name, interval, _handler, description=f"Cron entry from distribution.yaml")
        registered += 1
        logger.debug("cron_loader: registered '%s' (every %ds, goal=%s)", name, interval, goal)

    # Built-in: Tool auto-improvement/deprecation check (C4) — runs daily
    try:
        async def _tool_evolution_handler():
            from core.harness.optimization.tool_evolution import get_regenerator
            regen = get_regenerator()
            improved = await regen.regenerate_underperforming()
            if improved:
                logger.info("ToolEvolution: %d changes — %s", len(improved), improved[:3])
        scheduler.register("tool_regeneration", 86400, _tool_evolution_handler,
                          description="Daily tool auto-improvement/deprecation check (C4)")
        registered += 1
    except Exception as e:
        logger.debug("tool_regeneration cron registration skipped: %s", e)

    return registered
