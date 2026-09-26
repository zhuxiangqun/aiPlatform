"""V1-pre — org run and K5 scan refuse to start when edge auto-apply is on.

The env switch stays. This guard does not delete it and does not touch the
old case-learning path. It only blocks the two entry points named in the V charter.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REASON = "edge_auto_apply_forbidden"


def edge_auto_apply_switch_on() -> bool:
    return os.getenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def edge_auto_apply_block() -> Optional[Dict[str, Any]]:
    """Return a refusal dict, or None when the switch is off."""
    if not edge_auto_apply_switch_on():
        return None
    logger.warning(REASON)
    return {
        "status": REASON,
        "reason": REASON,
        "auto_apply": False,
        "created_count": 0,
        "created": [],
        "skipped": [],
    }
