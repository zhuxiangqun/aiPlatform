"""
Loop Trigger API (event-driven pipeline).
"""

from typing import Any, Dict
from fastapi import APIRouter, Body
from pydantic import BaseModel

router = APIRouter(tags=["wiki-loop-triggers"])


class TriggerRegisterRequest(BaseModel):
    trigger_id: str = ""
    mode: str = "cron"              # cron | webhook | goal
    scene_id: str = ""
    cron_expression: str = ""       # "0 6 * * *"
    webhook_pattern: str = ""       # "github_pr" | "jira_ticket" | "*"
    params: Dict[str, Any] = {}


@router.post("/triggers", response_model=Dict[str, Any])
async def register_loop_trigger(req: TriggerRegisterRequest):
    """Register a pipeline trigger (cron/webhook/goal)."""
    from core.harness.execution.event_loop import register_trigger, Trigger
    t = Trigger(
        trigger_id=req.trigger_id or f"trigger_{int(__import__('time').time())}",
        mode=req.mode, scene_id=req.scene_id, params=req.params,
        cron_expression=req.cron_expression, webhook_pattern=req.webhook_pattern,
    )
    register_trigger(t)
    return {"status": "ok", "trigger": t.to_dict()}


@router.get("/triggers", response_model=Dict[str, Any])
async def list_loop_triggers():
    """List all registered pipeline triggers."""
    from core.harness.execution.event_loop import load_triggers
    triggers = load_triggers()
    return {"triggers": [t.to_dict() for t in triggers], "total": len(triggers)}


@router.delete("/triggers/{trigger_id}", response_model=Dict[str, Any])
async def remove_loop_trigger(trigger_id: str):
    """Remove a pipeline trigger."""
    from core.harness.execution.event_loop import remove_trigger
    ok = remove_trigger(trigger_id)
    return {"status": "ok" if ok else "not_found"}


@router.post("/webhook", response_model=Dict[str, Any])
async def handle_webhook(source: str = Body(...), payload: Dict[str, Any] = Body(default={})):
    """Handle incoming webhook — dispatches to matching triggers."""
    from core.harness.execution.event_loop import dispatch_webhook
    count = await dispatch_webhook(source, payload)
    return {"triggered": count}
