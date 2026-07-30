"""Code intelligence router — stub, implementation pending.

Used by change_control.py which fails open when this is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def repo_root() -> str:
    logger.debug("code_intel.repo_root: stub")
    return ""


def default_roots() -> list[str]:
    logger.debug("code_intel.default_roots: stub")
    return []


async def code_intel_scan(runtime: Any, roots: list[str]) -> Any:
    logger.debug("code_intel.code_intel_scan: stub")
    return _StubScan()


class _StubScan:
    stats: dict = {"nodes": 0, "edges": 0}
    health: str = "unavailable"


def blast(nodes: Any, rel_path: str) -> list[dict]:
    logger.debug("code_intel.blast: stub")
    return []
