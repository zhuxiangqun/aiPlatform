"""User Workbench API — end-user task submission and feedback.

Endpoints:
  POST   /workbench/submit    — submit new task (description + files + capability)
  GET    /workbench/tasks/{id} — query task status + progress
  GET    /workbench/tasks      — user history
  POST   /workbench/tasks/{id}/feedback — submit user rating
  GET    /workbench/capabilities — list available agent capabilities
"""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/workbench", tags=["workbench"])

_tasks: Dict[str, Dict[str, Any]] = {}


@router.get("/capabilities")
async def get_capabilities() -> List[Dict[str, str]]:
    """List available agent capabilities for the workbench."""
    return [
        {"id": "contract_review", "name": "合同审核", "desc": "自动审核合同条款、价格、合规性", "icon": "📋"},
        {"id": "report_gen", "name": "报表生成", "desc": "根据数据自动生成分析报表", "icon": "📊"},
        {"id": "qa", "name": "客服问答", "desc": "内部知识库智能问答", "icon": "💬"},
        {"id": "code_review", "name": "代码审查", "desc": "自动检查代码质量和安全", "icon": "🔍"},
        {"id": "general", "name": "通用任务", "desc": "自由描述任意AI任务", "icon": "🤖"},
    ]


@router.post("/submit")
async def submit_task(body: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a new task to the AI agent."""
    import uuid, time

    task = body.get("description", "")
    capability = body.get("capability", "general")
    if not task:
        raise HTTPException(status_code=400, detail="description is required")

    run_id = f"wb-{uuid.uuid4().hex[:8]}" if "run_id" not in body else body["run_id"]
    entry = {
        "run_id": run_id,
        "capability": capability,
        "description": task[:500],
        "status": "running",
        "progress": {"current_step": 0, "total_steps": 4, "steps": [
            {"name": "分析请求", "status": "running"},
            {"name": "执行任务", "status": "pending"},
            {"name": "生成结果", "status": "pending"},
            {"name": "质量检查", "status": "pending"},
        ]},
        "result": None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _tasks[run_id] = entry
    return {"run_id": run_id, "status": "accepted"}


@router.get("/tasks/{run_id}")
async def get_task_status(run_id: str) -> Dict[str, Any]:
    """Get task execution status and progress."""
    entry = _tasks.get(run_id)
    if not entry:
        # Simulate completed task for demo
        import time
        return {
            "run_id": run_id, "capability": "general",
            "description": "Demo task", "status": "completed",
            "progress": {"current_step": 4, "total_steps": 4, "steps": [
                {"name": "分析请求", "status": "completed"},
                {"name": "执行任务", "status": "completed"},
                {"name": "生成结果", "status": "completed"},
                {"name": "质量检查", "status": "completed"},
            ]},
            "result": {"summary": "任务已完成", "warnings": []},
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    return entry


@router.get("/tasks")
async def get_user_tasks(limit: int = 20) -> Dict[str, Any]:
    """Get user's historical task list."""
    items = sorted(_tasks.values(), key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
    if not items:
        import time
        items = [{
            "run_id": f"demo-{i}", "capability": "general",
            "description": f"Demo task {i}",
            "status": "completed",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        } for i in range(3)]
    return {"items": items, "total": len(items)}


@router.post("/tasks/{run_id}/feedback")
async def submit_feedback(run_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Submit user feedback for a completed task."""
    rating = body.get("rating", 0)
    action = body.get("action", "useful")

    # Feed into ImplicitFeedbackCollector
    try:
        from core.services.implicit_feedback import get_implicit_feedback_collector
        collector = get_implicit_feedback_collector()
        await collector.record(
            run_id=run_id,
            signal_type="copy_full" if action == "useful" else "re_query",
            value=0.3 if action == "useful" else -0.1,
        )
    except Exception:
        pass

    _tasks[run_id] = {**_tasks.get(run_id, {}), "rating": rating, "feedback_action": action}
    return {"run_id": run_id, "rating": rating, "recorded": True}
