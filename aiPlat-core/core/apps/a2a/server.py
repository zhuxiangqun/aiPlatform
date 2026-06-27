"""A2A Server — Google A2A protocol endpoints, backed by aiPlat infrastructure.

Reuses: ExecutionStore (task persistence), core_chat (execution),
        ReActLoop SSE (streaming), SkillRegistry (Agent Card).

Zero new dependencies.
"""

from __future__ import annotations
import logging

import json
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import asyncio

from .agent_card import AgentCard
from .types import Task, TaskStatus

a2a_router = APIRouter(prefix="/a2a", tags=["a2a"])

_tasks: Dict[str, Task] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 1. Agent Card ──────────────────────────────────

@a2a_router.get("/.well-known/agent.json")
async def get_agent_card(request: Request):
    base = str(request.base_url).rstrip("/")
    card = await AgentCard.from_registry(base)
    return card.to_dict()


# ── 2. Submit task ─────────────────────────────────

@a2a_router.post("/tasks")
async def create_task(request: Request):
    body = await request.json()
    user_input = str(body.get("user_input") or body.get("task", {}).get("description", ""))
    if not user_input:
        raise HTTPException(400, "user_input required")

    task_id = body.get("task_id") or str(uuid.uuid4())
    task = Task(
        id=task_id, status=TaskStatus.PENDING,
        user_input=user_input, created_at=_now(), updated_at=_now(),
    )
    _tasks[task_id] = task
    asyncio.create_task(_execute_task(task_id, user_input))

    return {"task_id": task_id, "status": task.status.value, "created_at": task.created_at}


async def _execute_task(task_id: str, user_input: str):
    task = _tasks.get(task_id)
    if not task:
        return
    task.status = TaskStatus.RUNNING
    task.updated_at = _now()

    try:
        from core.api.intents import core_chat
        result = await core_chat(user_input=user_input)
        output = result.get("message") or result.get("output") or str(result) if isinstance(result, dict) else str(result)
        task.result = {"output": output}
        task.status = TaskStatus.COMPLETED

        try:
            from core.harness.memory.manager import get_memory_manager
            mm = get_memory_manager()
            for ts_id, ts in getattr(mm, '_task_skills', {}).items():
                task.artifacts.append({"id": ts_id, "name": ts.name, "pass_rate": ts.pass_rate})
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)[:500]

    task.updated_at = _now()


# ── 3. Get task ────────────────────────────────────

@a2a_router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            run = await store.get_run(task_id)
            if run:
                return {"task_id": task_id, "status": getattr(run, "status", "completed"),
                        "result": getattr(run, "output", None)}
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise HTTPException(404, "task_not_found")

    return {"task_id": task.id, "status": task.status.value, "user_input": task.user_input,
            "result": task.result, "error": task.error,
            "created_at": task.created_at, "updated_at": task.updated_at,
            "artifacts_count": len(task.artifacts)}


# ── 4. Stream task ─────────────────────────────────

@a2a_router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    async def event_generator():
        task = _tasks.get(task_id)
        if not task:
            yield f"data: {json.dumps({'error': 'task_not_found'})}\n\n"
            return
        yield f"data: {json.dumps({'type': 'status', 'status': task.status.value})}\n\n"
        last_len = 0
        while task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            events = task.events[last_len:]
            for evt in events:
                yield f"data: {json.dumps({'type': evt.type, 'data': evt.data})}\n\n"
            last_len = len(task.events)
            await asyncio.sleep(0.2)
        yield f"event: done\ndata: {json.dumps({'type': 'final', 'status': task.status.value, 'result': task.result})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── 5. Cancel task ─────────────────────────────────

@a2a_router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "task_not_found")
    if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(409, f"task already {task.status.value}")
    task.status = TaskStatus.CANCELLED
    task.updated_at = _now()
    return {"task_id": task_id, "status": "cancelled"}


# ── 6. Get artifacts ───────────────────────────────

@a2a_router.get("/tasks/{task_id}/artifacts")
async def get_task_artifacts(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "task_not_found")
    return {"task_id": task_id, "artifacts": task.artifacts, "count": len(task.artifacts)}


# ── 7. List tasks ──────────────────────────────────

@a2a_router.get("/tasks")
async def list_tasks(status: str = None, limit: int = 50):
    tasks = list(_tasks.values())
    if status:
        tasks = [t for t in tasks if t.status.value == status]
    tasks.sort(key=lambda t: t.created_at or "", reverse=True)
    return {"tasks": [{"task_id": t.id, "status": t.status.value, "created_at": t.created_at}
                      for t in tasks[:limit]], "total": len(tasks)}
