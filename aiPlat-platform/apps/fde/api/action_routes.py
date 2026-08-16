"""
Action execution REST API — list available actions and execute them.

Mounted at: /api/platform/apps/fde/actions
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["fde-actions"])

logger = logging.getLogger(__name__)


def _safe_contract(contract) -> Dict[str, Any]:
    """Extract frontend-safe fields from ActionContractModel (no handler paths)."""
    return {
        "action_id": contract.action_id,
        "label": contract.label,
        "description": contract.description,
        "category": contract.category.value,
        "scope": contract.scope.value,
        "domain_id": contract.domain_id,
        "target_class": contract.target_class,
        "required_state": contract.required_state,
        "forbidden_states": contract.forbidden_states,
        "effect_semantics": contract.effect_semantics,
        "compensation": contract.compensation,
        "risk_level": contract.risk_level.value,
        "require_approval": contract.require_approval,
        "input_schema": contract.input_schema,
    }


@router.get("/actions")
async def list_actions(
    class_name: str = Query("", description="Entity class to filter actions for"),
    state: str = Query("", description="Entity state to filter actions for"),
    domain: str = Query("", description="Domain ID"),
    role: str = Query("", description="Caller's role (optional)"),
    include_cross_domain: bool = Query(False, description="Include cross-domain actions"),
):
    """List actions available for a given entity class + state."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        actions = reg.list_for_class(
            domain_id=domain or "fde-delivery",
            class_name=class_name,
            state=state,
            role=role,
            include_cross_domain=include_cross_domain,
        )
        return {"actions": [_safe_contract(a) for a in actions], "count": len(actions)}
    except Exception as e:
        logger.error("Failed to list actions: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/execute")
async def execute_action(body: Dict[str, Any]):
    """Execute a registered action.

    Body:
      action_id  — registered action identifier
      entity_id  — target entity ID (str) or [domain, entity_id] for cross-domain
      params     — input parameters matching action.input_schema
      actor      — who triggered the action (optional)
      role       — actor's role for constraint checking (optional)
    """
    action_id = str(body.get("action_id", "")).strip()
    entity_ref = body.get("entity_id")
    params = body.get("params", {}) or {}
    actor = str(body.get("actor", "system"))
    role = str(body.get("role", ""))

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id is required")

    if not entity_ref:
        raise HTTPException(status_code=400, detail="entity_id is required")

    # Support cross-domain tuple: entity_ref = ["domain_id", "entity_id"]
    if isinstance(entity_ref, list):
        if len(entity_ref) >= 2:
            entity_ref = (str(entity_ref[0]), str(entity_ref[1]))
        else:
            entity_ref = str(entity_ref[0])

    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        result = await reg.execute(
            action_id=action_id,
            entity_ref=entity_ref,
            params=params,
            actor=actor,
            role=role,
        )

        # Map constraint types to HTTP-friendly responses
        status = result.get("status", "unknown")
        if status == "blocked":
            return {
                "status": "blocked",
                "reason": result.get("reason", "Unknown constraint"),
                "constraint_type": result.get("constraint_type", "unknown"),
            }
        if status == "pending_approval":
            return {
                "status": "pending_approval",
                "action_id": result.get("action_id"),
                "entity_id": result.get("entity_id"),
                "lock_id": result.get("lock_id"),
                "locked_until": result.get("locked_until"),
                "message": result.get("message", "Approval required"),
            }
        if status == "invalid_params":
            raise HTTPException(status_code=400, detail=result.get("errors", ["Invalid params"]))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Action execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/from-yaml")
async def register_from_yaml(body: Dict[str, Any]):
    """Register actions from a YAML file (business expert entry point).

    Body:
      yaml_path  — path to YAML file (must be within ~/.aiplat/actions/ or ./config/actions/)
    """
    yaml_path = str(body.get("yaml_path", "")).strip()
    if not yaml_path:
        raise HTTPException(status_code=400, detail="yaml_path is required")

    try:
        from core.api.core_facade import ActionContractModel
        from core.api.core_facade import get_action_registry

        contracts = ActionContractModel.from_yaml_batch(yaml_path)
        reg = get_action_registry()
        count = reg.register_batch(contracts)

        return {
            "status": "registered",
            "registered_count": count,
            "action_ids": [c.action_id for c in contracts],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("YAML registration failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)[:300])


# ═══════════════════════════════════════════════════════════
# Approval workflow
# ═══════════════════════════════════════════════════════════

@router.get("/actions/approvals/pending")
async def list_pending_approvals(
    entity_ref: str = Query("", description="Filter by entity (domain:entity_id)"),
):
    """List pending approval requests."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        items = await reg._store.list_pending_by_entity(entity_ref) if entity_ref else []
        return {"pending": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/approvals/{lock_id}/approve")
async def approve_action(lock_id: str, body: Dict[str, Any] = None):
    """Approve a pending action."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        result = await reg.approve(lock_id, resolver=body.get("resolver", "approver") if body else "approver")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/approvals/{lock_id}/reject")
async def reject_action(lock_id: str, body: Dict[str, Any] = None):
    """Reject a pending action."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        result = await reg.reject(
            lock_id,
            resolver=body.get("resolver", "approver") if body else "approver",
            reason=body.get("reason", "") if body else "",
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])
