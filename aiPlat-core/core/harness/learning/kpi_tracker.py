"""KPI tracker — stub, implementation pending.

Tracked by fde_acceptance.py which gracefully falls back to 'KPI tracker 不可用'.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class KPITracker:
    def get_all(self, spec_id: str | None = None) -> list[dict]:
        logger.debug("KPITracker.get_all: stub")
        return []


_tracker: KPITracker | None = None


def get_kpi_tracker() -> KPITracker:
    global _tracker
    if _tracker is None:
        _tracker = KPITracker()
    return _tracker
