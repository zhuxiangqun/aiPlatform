"""Ollaya / typed-decision shadow skeleton (muted by default).

Honesty:
  - Default ``enabled=false``; no DomainRouter.classify hook in this PR.
  - ≠ live Ollaya traffic; ≠ token savings; ≠ Phase 1b T3 replace.
  - Opening sample traffic still requires written Go / narrower waiver.
"""

from core.harness.decision_shadow.audit import AUDIT_FIELD_WHITELIST, redact_payload
from core.harness.decision_shadow.client import DecisionClient
from core.harness.decision_shadow.config import (
    DecisionShadowConfig,
    load_decision_shadow_config,
)
from core.harness.decision_shadow.dispatcher import (
    ShadowDispatcher,
    get_shadow_dispatcher,
    reset_shadow_dispatcher_for_tests,
)

__all__ = [
    "AUDIT_FIELD_WHITELIST",
    "DecisionClient",
    "DecisionShadowConfig",
    "ShadowDispatcher",
    "get_shadow_dispatcher",
    "load_decision_shadow_config",
    "redact_payload",
    "reset_shadow_dispatcher_for_tests",
]
