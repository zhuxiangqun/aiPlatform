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
        """初始化。

        Args:
            config: config 参数。
        """
        self._config = config

    @property
    def configured(self) -> bool:
        """configured。
        """
        return bool(self._config.endpoint)

    def score(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous score call. Skeleton refuses unless endpoint set.

        Args:
            payload: 载荷 dict。
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
