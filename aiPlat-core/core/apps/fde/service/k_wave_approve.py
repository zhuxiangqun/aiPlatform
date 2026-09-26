"""V4 — proposal approval is one PolicyGate decision. Approve does not write YAML."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def approve_proposal_once(proposal_id: str, *, role: str) -> Dict[str, Any]:
    """Identity is the caller role. Body roles are not consulted."""
    from core.apps.fde.service.k_wave_signal import live_yaml_hash
    from core.harness.infrastructure.action_store import ActionStore
    from core.harness.infrastructure.gates.policy_gate import PolicyDecision, PolicyGate
    from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

    store = ActionStore()
    await store.initialize()
    proposal = await store.get_ontology_proposal(proposal_id)
    if not proposal:
        return {
            "success": False,
            "status": "not_found",
            "reason": "proposal not found",
            "live_yaml_written": False,
        }
    impact = json.loads(proposal.get("impact_analysis") or "{}") or {}
    tier = str(impact.get("max_tier") or "logic")
    decision = PolicyGate().decide_ontology_approval(role, tier)
    if decision.decision != PolicyDecision.ALLOW:
        return {
            "success": False,
            "status": "rejected",
            "reason": decision.reason or "policy_denied",
            "live_yaml_written": False,
        }
    domain_id = str(proposal.get("domain_id") or "it-ops")
    before = live_yaml_hash(domain_id)
    result = await VersionedOntologyStore(domain_id).approve_proposal(
        proposal_id,
        approver_role=role,
        gate_passed=True,
    )
    after = live_yaml_hash(domain_id)
    result["live_yaml_written"] = before != after
    result["live_yaml_unchanged"] = before == after
    if before != after:
        logger.error("approve wrote live yaml proposal=%s", proposal_id)
    return result
