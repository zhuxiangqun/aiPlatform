"""Workbench runtime checks (FDE Phase 1 skeleton).

Extends AsyncActionRegistry / Facade — does NOT create FdeActionRegistry.
Maps to docs/contracts/FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md §1 items 4/6/9.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Set


# KPI keys that Phase 0 marked as stubs — must not be presented as live ops health.
_STUB_KPI_KEYS: Set[str] = {
    "pending_decisions",
    "trace_anomalies",
    "training",
}


class WorkbenchRuntimeGuard:
    """Runtime guards for FDE workbench honesty + Action entry checks."""

    @staticmethod
    def check_action_registered(registry: Any, action_id: str) -> Dict[str, Any]:
        """Item 4: refuse unregistered Action ids before execute."""
        get = getattr(registry, "get", None)
        if not callable(get):
            return {"ok": False, "reason": "registry_missing_get", "action_id": action_id}
        contract = get(action_id)
        if contract is None:
            return {"ok": False, "reason": "action_not_registered", "action_id": action_id}
        return {"ok": True, "action_id": action_id}

    @staticmethod
    def check_policy_gate_called(
        *,
        action_namespace: str = "",
        policy_gate_decision: Optional[Mapping[str, Any]] = None,
        skip_if_legacy: bool = True,
    ) -> Dict[str, Any]:
        """Item 6: customer_action audits must carry policy_gate_decision (Phase 1 soft).

        Full PolicyGate product surface remains Phase 2; this only asserts the audit shape.
        """
        if skip_if_legacy and not action_namespace:
            return {"ok": True, "skipped": True}
        if action_namespace != "customer_action":
            return {"ok": True, "skipped": True}
        if not policy_gate_decision:
            return {"ok": False, "reason": "policy_gate_decision_missing"}
        decision = policy_gate_decision.get("decision")
        if decision not in {"allow", "deny", "hitl_required"}:
            return {"ok": False, "reason": "policy_gate_decision_invalid", "decision": decision}
        return {"ok": True, "decision": decision}

    @staticmethod
    def check_kpi_not_stub(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Item 9: flag stub KPI keys presented as operational metrics."""
        flagged = []
        for key in _STUB_KPI_KEYS:
            if key not in payload:
                continue
            val = payload[key]
            # Empty list / empty dict / explicit stub marker → stub
            if val in (None, [], {}, {"stub": True}):
                flagged.append(key)
            elif isinstance(val, dict) and val.get("stub") is True:
                flagged.append(key)
        return {
            "ok": len(flagged) == 0,
            "stub_keys": flagged,
            "reason": "stub_kpi_present" if flagged else "",
        }
