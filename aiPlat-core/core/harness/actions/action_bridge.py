"""Action Bridge — OperatorAgent decisions → ontology Action Types → execution.

Closes the loop: when OperatorAgent recommends actions (notify, create ticket,
adjust schedule), these are mapped to Action Type YAML definitions and executed
via webhook/business logic.

Usage:
    from core.harness.actions.action_bridge import execute_decision_actions

    result = await execute_decision_actions(decision_json, context={
        "entity_id": "注塑机#3",
        "domain_id": "factory-ops",
    })
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.action_bridge")


async def execute_decision_actions(
    decision: Dict[str, Any],
    *,
    context: Optional[Dict[str, Any]] = None,
    webhook_url: str = "",
) -> List[Dict[str, Any]]:
    """Execute recommended actions from an OperatorAgent decision.

    For each recommended action, creates a webhook payload and fires it.
    The webhook receiver handles the actual business logic.

    Args:
        decision: OperatorAgent output (must have recommended_actions list).
        context: Runtime context including entity_id, domain_id, timestamp.
        webhook_url: Default webhook URL for actions without specific targets.

    Returns:
        List of action results with status for each.
    """
    ctx = context or {}
    actions = decision.get("recommended_actions", [])
    if not actions:
        return []

    results: List[Dict[str, Any]] = []
    for i, action in enumerate(actions):
        action_name = str(action.get("action", f"action_{i}"))
        target = str(action.get("target", ""))
        urgency = str(action.get("urgency", "within_24h"))

        payload = {
            "event": "operator_decision_action",
            "action": action_name,
            "target": target,
            "urgency": urgency,
            "severity": decision.get("severity", "normal"),
            "entity_id": ctx.get("entity_id", ""),
            "domain_id": ctx.get("domain_id", "default"),
            "can_continue": decision.get("can_continue", True),
            "decision_rationale": decision.get("decision_rationale", ""),
            "timestamp": ctx.get("timestamp", ""),
            "note": str(action.get("note", "")),
        }

        url = webhook_url or ctx.get("webhook_url", "")
        result: Dict[str, Any] = {
            "action": action_name,
            "target": target,
            "urgency": urgency,
            "webhook_fired": False,
        }

        if url:
            try:
                await _fire_webhook(url, payload)
                result["webhook_fired"] = True
                result["status"] = "sent"
            except Exception as e:
                result["status"] = "failed"
                result["error"] = str(e)
                logger.warning("Webhook fire failed for action '%s': %s", action_name, e)
        else:
            result["status"] = "no_url"
            logger.info("Action '%s' logged (no webhook URL configured): %s", action_name, payload)

        results.append(result)

    return results


async def _fire_webhook(url: str, payload: Dict[str, Any]) -> None:
    """Fire a webhook via aiohttp. Best-effort; does not block the main flow."""
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status >= 400:
                    logger.warning("Webhook %s returned status %d", url, resp.status)
    except Exception as e:
        logger.debug("Webhook %s failed: %s", url, e)
        raise
