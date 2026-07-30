"""Kanban Task Board — REST API (A2.3 看板+Cron 定时调度).

Exposes the KanbanEngine task board via 4 endpoints so the diagnostics
center / System Overview / a future Kanban UI can read and manage tasks.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from apps.common_schemas import StatusResponse, ListResponse, ItemResponse

router = APIRouter(tags=["kanban"])

log = logging.getLogger("aiplat.kanban")


class TaskCreate(BaseModel):
    title: str
    profile_id: str = "default"
    description: str = ""
    priority: int = 5
    depends_on: Optional[List[str]] = None


class StatusUpdate(BaseModel):
    to_status: str
    reason: str = ""


@router.get("/kanban/tasks", response_model=ItemResponse)
async def get_kanban_tasks(profile: str = Query("default"), status: Optional[str] = None):
    """List tasks for a profile, optionally filtered by status. Returns tasks
    grouped by status for a kanban board view."""
    from core.api.core_facade import KanbanEngine
    kb = KanbanEngine()
    tasks = kb.list_tasks(profile, status=status)
    grouped: Dict[str, list] = {}
    for t in tasks:
        st = t.get("status", "unknown")
        grouped.setdefault(st, []).append({
            "task_id": t.get("task_id"), "title": t.get("title"),
            "status": st, "priority": t.get("priority"),
            "scheduled_at": t.get("scheduled_at"), "created_at": t.get("created_at"),
            "retry_count": t.get("retry_count"), "max_retries": t.get("max_retries"),
        })
    return {"profile": profile, "total": len(tasks), "by_status": grouped, "tasks": tasks}


@router.post("/kanban/tasks", response_model=StatusResponse)
async def create_kanban_task(body: TaskCreate):
    """Manually create a kanban task (for UI or admin debugging)."""
    from core.api.core_facade import KanbanEngine
    kb = KanbanEngine()
    tid = kb.create_task(profile_id=body.profile_id, title=body.title,
                         description=body.description, priority=body.priority,
                         depends_on=body.depends_on)
    return {"task_id": tid, "status": "pending", "profile": body.profile_id}


@router.patch("/kanban/tasks/{task_id}/status", response_model=StatusResponse)
async def update_kanban_task_status(task_id: str, body: StatusUpdate):
    """Transition a task to a new status (block/retry/close)."""
    from core.api.core_facade import KanbanEngine
    kb = KanbanEngine()
    ok = kb.transition_task(task_id, body.to_status, reason=body.reason)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Cannot transition {task_id} → {body.to_status}")
    return {"task_id": task_id, "new_status": body.to_status}


@router.get("/health/kanban", response_model=ItemResponse)
async def kanban_health(profile: str = Query("default")):
    """Kanban health summary: total/todo/blocked/overdue counts."""
    from core.api.core_facade import KanbanEngine
    kb = KanbanEngine()
    all_tasks = kb.list_tasks(profile)
    counts = {"total": len(all_tasks)}
    for t in all_tasks:
        st = t.get("status", "unknown")
        counts[st] = counts.get(st, 0) + 1
    return {"profile": profile, "counts": counts, "healthy": counts.get("blocked", 0) < 5}
