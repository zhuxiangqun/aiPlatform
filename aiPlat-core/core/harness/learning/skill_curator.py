"""
Skill Curator — unified lifecycle entry (P1-A2).

Delegates to the authoritative implementation in core/apps/skills/curator.py
(file-directory lifecycle: active→stale→archived + merge + restore).

This module provides the canonical import path (harness/learning/) and a
synchronous scan() API for diagnostics/review workflows. The async
run_if_idle() path is wired into the nightly cron scheduler
(core/harness/scheduler/cron.py via integration.get_skill_curator()).

History: two parallel implementations existed (apps/skills/curator.py and
harness/knowledge/skill_curator.py). apps/skills/curator.py is the
authoritative one (more complete: merge/template/restore, wired to cron).
knowledge/skill_curator.py remains for registry-state transitions used by
system.py endpoints; both share this entry's lifecycle semantics.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SkillCurator:
    """Unified skill lifecycle curator facade (P1-A2)."""

    def __init__(self, skill_dir: Optional[Path] = None, config: Optional[Any] = None):
        from core.apps.skills.curator import SkillCurator as _Impl, CuratorConfig
        self._impl = _Impl(skill_dir=skill_dir, config=config or CuratorConfig())

    def scan(self) -> Dict[str, Any]:
        """Synchronous scan: review skill lifecycle and return a report.

        Returns dict with 'stale'/'archived'/'active'/'merged'/'promoted' keys.
        """
        # The authoritative impl is async; run it to completion synchronously.
        try:
            import asyncio as _a
            loop = _a.new_event_loop()
            try:
                report = loop.run_until_complete(self._impl._run())
            finally:
                loop.close()
        except Exception as e:
            logger.debug("curator scan failed: %s", e, exc_info=True)
            return {"error": str(e)[:200], "reviewed": 0}
        return {
            "stale": [],
            "archived": [],
            "active": report.active_count,
            "stale_count": report.stale_count,
            "archived_count": report.archived_count,
            "merged": report.merged,
            "promoted": report.promoted,
            "reviewed": report.active_count + report.stale_count + report.archived_count,
        }

    async def run_if_idle(self) -> Any:
        """Async nightly path (delegated to cron wiring)."""
        return await self._impl.run_if_idle()

    def record_call(self, skill_id: str) -> None:
        """Record a skill invocation for lifecycle tracking."""
        self._impl.record_call(skill_id)


def _has_running_loop() -> bool:
    try:
        import asyncio as _a
        return _a.get_event_loop().is_running()
    except Exception:
        return False


def get_skill_curator(skill_dir: Optional[Path] = None) -> SkillCurator:
    """Get the unified curator facade."""
    return SkillCurator(skill_dir=skill_dir)
