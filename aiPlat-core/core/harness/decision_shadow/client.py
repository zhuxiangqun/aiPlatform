"""Decision service client stub (Ollaya / typed-decision HTTP).

Skeleton: no network I/O unless endpoint is configured AND caller opts in.
DomainRouter does not call this yet.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.harness.decision_shadow.config import DecisionShadowConfig

logger = logging.getLogger(__name__)


class DecisionClient:
    """Thin adapter placeholder — HTTP details stay isolated here."""

    def __init__(self, config: DecisionShadowConfig):
        self._config = config

    @property
    def configured(self) -> bool:
        return bool(self._config.endpoint)

    def score(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous score call. Skeleton refuses unless endpoint set.

        Production Phase 1 worker will use timeout_ms + async path; this stub
        exists so unit tests can assert isolation without network.
        """
        if not self._config.enabled:
            return {"ok": False, "drop_reason": "disabled"}
        if not self.configured:
            return {"ok": False, "drop_reason": "endpoint_empty"}
        # Intentionally unimplemented network path in skeleton.
        logger.debug(
            "DecisionClient.score refused (skeleton; no HTTP). keys=%s",
            sorted(payload.keys()),
        )
        return {"ok": False, "drop_reason": "skeleton_no_http"}
