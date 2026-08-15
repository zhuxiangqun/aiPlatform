"""
Skill Curator — unified lifecycle entry (P1-A2).

Delegates to the harness-layer implementation in
core/harness/knowledge/skill_curator.py (registry-state lifecycle:
active→stale→archived via SkillRegistry binding stats).

This module provides the canonical import path (harness/learning/) and a
synchronous scan() API for diagnostics/review workflows, plus a
run_if_idle() wrapper for the nightly scheduler.

Boundary note: harness/ MUST NOT import core.apps.* (test_harness_does_not_
import_apps). The authoritative curator implementation used here lives in
harness/knowledge/ — the parallel apps/skills/curator.py remains wired via
core/harness/integration.py for cron, but harness/learning does not reach
into apps.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SkillCurator:
    """Unified skill lifecycle curator facade (P1-A2)."""

    def __init__(self, skill_dir: Optional[Any] = None, config: Optional[Any] = None):
        from core.harness.knowledge.skill_curator import SkillCurator as _Impl
        self._impl = _Impl()

    def scan(self) -> Dict[str, Any]:
        """Synchronous scan: review skill lifecycle and return a report.

        Returns dict with 'stale'/'archived'/'merge_suggestions'/'reviewed' keys.
        """
        try:
            return self._impl.curate()
        except Exception as e:
            logger.debug("curator scan failed: %s", e, exc_info=True)
            return {"error": str(e)[:200], "reviewed": 0}

    async def run_if_idle(self) -> Dict[str, Any]:
        """Async nightly path — knowledge curator has built-in interval control."""
        return self._impl.curate()

    def record_call(self, skill_id: str) -> None:
        """Record a skill invocation for lifecycle tracking (no-op on registry impl)."""
        # registry-state curator tracks via SkillBindingStats; nothing to do here
        pass


def get_skill_curator(skill_dir: Optional[Any] = None) -> SkillCurator:
    """Get the unified curator facade."""
    return SkillCurator(skill_dir=skill_dir)
