"""Business event bridge (P0-L2, 六层框架 GPS 层).

Turns business actions into event-driven, incremental GraphIndex instance
updates — replacing "periodic ABox rebuild" for action-driven state changes:

    AsyncActionRegistry.execute (success)
      → publish_business_action
          ├─ emit BUSINESS_ACTION event on the observability EventBus (audit)
          └─ _apply_incremental_update → GraphIndex.add_entity/add_entity_property
             (upsert entity state immediately, no full rebuild)

The bridge is best-effort: a failure never blocks the originating action.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _apply_incremental_update(data: Dict[str, Any]) -> None:
    """Upsert the affected entity's latest action state into GraphIndex."""
    domain_id = data.get("domain_id") or "default"
    entity_id = str(data.get("entity_id") or "").strip()
    if not entity_id:
        return
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        g = GraphIndex.load(domain_id)
        g.add_entity(entity_id, entity_id, "BusinessEntity")
        g.add_entity_property(entity_id, "last_action", str(data.get("action_id") or ""))
        g.add_entity_property(entity_id, "last_status", str(data.get("status") or ""))
        g.add_entity_property(entity_id, "last_actor", str(data.get("actor") or ""))
        logger.info("business bridge: entity=%s action=%s status=%s (domain=%s)",
                    entity_id, data.get("action_id"), data.get("status"), domain_id)
    except Exception:
        logger.debug("business bridge incremental update failed", exc_info=True)


async def publish_business_action(*, action_id: str, entity_id: str, domain_id: str,
                                  result: Any = None, status: str = "",
                                  actor: str = "") -> None:
    """Publish a completed business action: emit audit event + incremental update.

    Never raises — the bridge is best-effort by design.
    """
    data: Dict[str, Any] = {
        "action_id": action_id,
        "entity_id": entity_id,
        "domain_id": domain_id,
        "status": status,
        "actor": actor,
        "result": str(result or "")[:500],
    }
    try:
        from core.harness.observability.events import EventBus, EventType

        EventBus.get_instance().emit(EventType.BUSINESS_ACTION, "action_registry", data=data)
    except Exception:
        logger.debug("business bridge emit failed", exc_info=True)
    _apply_incremental_update(data)
