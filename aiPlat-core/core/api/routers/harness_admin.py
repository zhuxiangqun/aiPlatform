from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import CoordinatorCreateRequest, FeedbackConfigUpdateRequest, HookCreateRequest, HookUpdateRequest

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _hm(rt: RuntimeDep):
    return getattr(rt, "harness_manager", None) if rt else None


# ==================== Harness Management ====================


@router.get("/harness/status")
async def get_harness_status(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get harness status"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    status = await hm.get_status()
    return {"status": status.status, "components": status.components, "uptime_seconds": status.uptime_seconds}


@router.get("/harness/config")
async def get_harness_config(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get harness config"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    config = await hm.get_config()
    return {
        "max_iterations": config.max_iterations,
        "timeout_seconds": config.timeout_seconds,
        "retry_count": config.retry_count,
        "retry_interval_seconds": config.retry_interval_seconds,
    }


@router.put("/harness/config")
async def update_harness_config(request: dict, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Update harness config"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    config = await hm.update_config(
        max_iterations=request.get("max_iterations"),
        timeout_seconds=request.get("timeout_seconds"),
        retry_count=request.get("retry_count"),
        retry_interval_seconds=request.get("retry_interval_seconds"),
    )
    return {"status": "updated", "config": config}


@router.get("/harness/metrics")
async def get_harness_metrics(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get harness metrics"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    metrics = await hm.get_metrics()
    return {"metrics": metrics}


@router.get("/harness/logs")
async def get_harness_logs(limit: int = 100, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get harness logs"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    logs = await hm.get_execution_logs(limit=limit)
    return {
        "logs": [{"id": l.id, "agent": l.agent, "status": l.status, "duration_ms": l.duration_ms, "start_time": l.start_time.isoformat() if l.start_time else None, "error": l.error} for l in logs]
    }


@router.get("/harness/hooks")
async def list_hooks(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """List hooks"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    hooks = await hm.get_hooks()
    return {"hooks": [{"id": h.id, "name": h.name, "type": h.type, "priority": h.priority, "enabled": h.enabled} for h in hooks]}


@router.post("/harness/hooks")
async def create_hook(request: HookCreateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Create hook"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    hook = await hm.add_hook(name=request.name, hook_type=request.type, priority=request.priority, config=request.config)
    return {"hook_id": hook.id, "status": "created"}


@router.delete("/harness/hooks/{hook_id}")
async def delete_hook(hook_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Delete hook"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    success = await hm.delete_hook(hook_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Hook {hook_id} not found")
    return {"status": "deleted"}


@router.put("/harness/hooks/{hook_id}")
async def update_hook(hook_id: str, request: HookUpdateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Update hook"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    hook = await hm.update_hook(hook_id, name=request.name, priority=request.priority, enabled=request.enabled, config=request.config)
    if not hook:
        raise HTTPException(status_code=404, detail=f"Hook {hook_id} not found")
    return {"status": "updated"}


@router.get("/harness/executions/{execution_id}")
async def get_harness_execution(execution_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get harness execution"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    execution = await hm.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return {"id": execution.id, "agent": execution.agent, "status": execution.status, "duration_ms": execution.duration_ms, "steps": execution.steps, "error": execution.error}


@router.get("/harness/coordinators")
async def list_coordinators(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """List coordinators"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    coordinators = await hm.list_coordinators()
    return {
        "coordinators": [{"id": c.id, "pattern": c.pattern, "agents": c.agents, "status": c.status, "created_at": c.created_at.isoformat() if c.created_at else None} for c in coordinators]
    }


@router.post("/harness/coordinators")
async def create_coordinator(request: CoordinatorCreateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Create coordinator"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    coordinator = await hm.create_coordinator(pattern=request.pattern, agents=request.agents, config=request.config)
    return {"coordinator_id": coordinator.id, "status": "created"}


@router.get("/harness/coordinators/{coordinator_id}")
async def get_coordinator(coordinator_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get coordinator"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    coordinator = await hm.get_coordinator(coordinator_id)
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Coordinator {coordinator_id} not found")
    return {"coordinator_id": coordinator.id, "pattern": coordinator.pattern, "agents": coordinator.agents, "status": coordinator.status, "config": coordinator.config}


@router.put("/harness/coordinators/{coordinator_id}")
async def update_coordinator(coordinator_id: str, request: dict):
    """Update coordinator"""
    # 保持旧实现：目前仅返回 updated（不执行实际更新）
    return {"status": "updated"}


@router.delete("/harness/coordinators/{coordinator_id}")
async def delete_coordinator(coordinator_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Delete coordinator"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    success = await hm.delete_coordinator(coordinator_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Coordinator {coordinator_id} not found")
    return {"status": "deleted"}


@router.get("/harness/feedback/config")
async def get_feedback_config(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get feedback config"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    config = await hm.get_feedback_config()
    return {"config": {"local": config.local, "push": config.push, "prod": config.prod}}


@router.put("/harness/feedback/config")
async def update_feedback_config(request: FeedbackConfigUpdateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Update feedback config"""
    hm = _hm(rt)
    if not hm:
        raise HTTPException(status_code=503, detail="HarnessManager not initialized")
    config = await hm.update_feedback_config(local=request.local, push=request.push, prod=request.prod)
    return {"status": "updated"}

