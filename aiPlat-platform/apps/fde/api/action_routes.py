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
    ns = getattr(contract, "action_namespace", "") or ""
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
        "action_namespace": ns,
        "action_kind": (
            "customer" if ns == "customer_action"
            else "platform" if ns == "platform_action"
            else "legacy"
        ),
        "aliases": list(getattr(contract, "aliases", None) or []),
    }


@router.get("/actions")
async def list_actions(
    class_name: str = Query("", description="Entity class to filter actions for", alias="class"),
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


@router.get("/graph/entities")
async def list_graph_entities(
    domain: str = Query(..., description="Domain ID"),
    class_name: str = Query("", alias="class", description="Entity class label"),
    limit: int = Query(50, ge=1, le=200),
):
    """List GraphIndex entities (for AcceptTab picker / live state)."""
    try:
        from core.api.core_facade import GraphIndex
        g = GraphIndex.load(domain)
        nodes = g.get_entities_by_class(class_name) if class_name else list(g._nodes.values())
        out = []
        for n in nodes[:limit]:
            meta = n.metadata or {}
            out.append({
                "entity_id": n.entity_id,
                "name": n.entity_name,
                "class": n.class_name,
                "state": meta.get("state") or meta.get("status") or "",
            })
        return {"domain": domain, "entities": out, "count": len(out)}
    except Exception as e:
        logger.error("list_graph_entities failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/graph/entities")
async def create_graph_entity(body: Dict[str, Any]):
    """Create a demo InstallOrder (and optional Technician) in GraphIndex.

    Body:
      domain_id — default lock-service
      class_name — default 安装工单
      entity_id — optional; auto IO-DEMO-xxx
      name — display name
      state — default pending
      with_technician — bool, also seed TECH-DEMO-001
    """
    domain_id = str(body.get("domain_id") or "lock-service")
    class_name = str(body.get("class_name") or "安装工单")
    state = str(body.get("state") or "pending")
    name = str(body.get("name") or "演示安装工单")
    with_tech = bool(body.get("with_technician", True))
    entity_id = str(body.get("entity_id") or "").strip()
    if not entity_id:
        import time
        entity_id = f"IO-DEMO-{int(time.time()) % 100000:05d}"

    try:
        from core.api.core_facade import GraphIndex
        GraphIndex._loaded_instances.clear()
        g = GraphIndex.load(domain_id)
        tech_id = str(body.get("technician_id") or "TECH-DEMO-001")
        if with_tech:
            g.add_entity(tech_id, "演示安装师傅", "安装师傅", source_doc_id="ui-demo")
        g.add_entity(entity_id, name, class_name, source_doc_id="ui-demo")
        g.add_entity_property(entity_id, "state", state)
        g.add_entity_property(entity_id, "status", state)
        g.save()
        return {
            "status": "created",
            "domain_id": domain_id,
            "entity_id": entity_id,
            "class": class_name,
            "state": state,
            "technician_id": tech_id if with_tech else None,
        }
    except Exception as e:
        logger.error("create_graph_entity failed: %s", e, exc_info=True)
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
