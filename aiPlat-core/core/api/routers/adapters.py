from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from core.governance.changeset import record_changeset
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import AdapterCreateRequest, AdapterUpdateRequest, ModelUpdateRequest

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


def _am(rt: RuntimeDep):
    return getattr(rt, "adapter_manager", None) if rt else None


async def _record_changeset(rt: RuntimeDep, **kwargs) -> None:
    store = _store(rt)
    return await record_changeset(store=store, **kwargs)


# ==================== Adapter Management ====================


@router.get("/adapters")
async def list_adapters(limit: int = 100, offset: int = 0, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """List adapters"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    adapters = await am.list_adapters(limit=limit, offset=offset)
    counts = am.get_adapter_count()
    return {
        "adapters": [{"adapter_id": a.id, "name": a.name, "provider": a.provider, "description": a.description, "status": a.status, "models": a.models} for a in adapters],
        "total": counts["total"],
    }


@router.post("/adapters")
async def create_adapter(request: AdapterCreateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Create adapter"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    adapter = await am.create_adapter(name=request.name, provider=request.provider, api_key=request.api_key, api_base_url=request.api_base_url, description=request.description)
    try:
        api_key_hash = hashlib.sha256(str(request.api_key).encode("utf-8")).hexdigest() if request.api_key else None
        await _record_changeset(
            rt,
            name="adapter_create",
            target_type="adapter",
            target_id=str(adapter.id),
            args={"name": request.name, "provider": request.provider, "api_base_url": request.api_base_url},
            result={"adapter_id": str(adapter.id), "api_key_sha256": api_key_hash, "api_key_len": len(str(request.api_key or ""))},
        )
    except Exception:
        pass
    return {"adapter_id": adapter.id, "status": "created"}


@router.get("/adapters/{adapter_id}")
async def get_adapter(adapter_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get adapter details"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    adapter = await am.get_adapter(adapter_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    return {
        "adapter_id": adapter.id,
        "name": adapter.name,
        "provider": adapter.provider,
        "description": adapter.description,
        "status": adapter.status,
        "api_base_url": adapter.api_base_url,
        "models": adapter.models,
        "rate_limit": adapter.rate_limit,
        "created_at": adapter.created_at.isoformat() if adapter.created_at else None,
    }


@router.put("/adapters/{adapter_id}")
async def update_adapter(adapter_id: str, request: AdapterUpdateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Update adapter"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    adapter = await am.update_adapter(
        adapter_id,
        name=request.name,
        description=request.description,
        api_key=request.api_key,
        api_base_url=request.api_base_url,
        rate_limit=request.rate_limit,
    )
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        api_key_hash = hashlib.sha256(str(request.api_key).encode("utf-8")).hexdigest() if request.api_key else None
        await _record_changeset(
            rt,
            name="adapter_update",
            target_type="adapter",
            target_id=str(adapter_id),
            args={"name": request.name, "api_base_url": request.api_base_url, "rate_limit": request.rate_limit},
            result={"api_key_sha256": api_key_hash, "api_key_len": len(str(request.api_key or "")) if request.api_key else 0},
        )
    except Exception:
        pass
    return {"status": "updated"}


@router.delete("/adapters/{adapter_id}")
async def delete_adapter(adapter_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Delete adapter"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    success = await am.delete_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(rt, name="adapter_delete", target_type="adapter", target_id=str(adapter_id), args={}, result={"status": "deleted"})
    except Exception:
        pass
    return {"status": "deleted"}


@router.post("/adapters/{adapter_id}/test")
async def test_adapter(adapter_id: str, request: dict, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Test adapter"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    return await am.test_connection(adapter_id)


@router.post("/adapters/{adapter_id}/enable")
async def enable_adapter(adapter_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Enable adapter"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    success = await am.enable_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(rt, name="adapter_enable", target_type="adapter", target_id=str(adapter_id), args={}, result={"status": "enabled"})
    except Exception:
        pass
    return {"status": "enabled"}


@router.post("/adapters/{adapter_id}/disable")
async def disable_adapter(adapter_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Disable adapter"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    success = await am.disable_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(rt, name="adapter_disable", target_type="adapter", target_id=str(adapter_id), args={}, result={"status": "disabled"})
    except Exception:
        pass
    return {"status": "disabled"}


@router.get("/adapters/{adapter_id}/models")
async def list_adapter_models(adapter_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """List adapter models"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    adapter = await am.get_adapter(adapter_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    return {"models": adapter.models}


@router.post("/adapters/{adapter_id}/models")
async def add_adapter_model(adapter_id: str, request: dict, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Add model to adapter"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    success = await am.add_model(
        adapter_id,
        request.get("name", "default"),
        request.get("max_tokens", 4096),
        request.get("temperature", 0.7),
        request.get("enabled", True),
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(
            rt,
            name="adapter_model_add",
            target_type="adapter",
            target_id=str(adapter_id),
            args={"model": request.get("name", "default"), "max_tokens": request.get("max_tokens", 4096), "temperature": request.get("temperature", 0.7), "enabled": request.get("enabled", True)},
            result={"status": "added"},
        )
    except Exception:
        pass
    return {"status": "added"}


@router.put("/adapters/{adapter_id}/models/{model_name}")
async def update_adapter_model(adapter_id: str, model_name: str, request: ModelUpdateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Update adapter model"""
    # 保持旧实现：目前仅返回 updated（不执行实际更新）
    return {"status": "updated"}


@router.delete("/adapters/{adapter_id}/models/{model_name}")
async def delete_adapter_model(adapter_id: str, model_name: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Delete adapter model"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    success = await am.remove_model(adapter_id, model_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(rt, name="adapter_model_delete", target_type="adapter", target_id=str(adapter_id), args={"model": str(model_name)}, result={"status": "deleted"})
    except Exception:
        pass
    return {"status": "deleted"}


@router.get("/adapters/{adapter_id}/stats")
async def get_adapter_stats(adapter_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get adapter stats"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    stats = await am.get_call_stats(adapter_id)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    success_rate = stats.success_count / stats.total_calls if stats.total_calls > 0 else 0
    return {
        "total_calls": stats.total_calls,
        "success_count": stats.success_count,
        "failed_count": stats.failed_count,
        "success_rate": success_rate,
        "avg_duration_ms": stats.avg_duration_ms,
        "tokens_used": stats.tokens_used,
    }


@router.get("/adapters/{adapter_id}/calls")
async def get_adapter_calls(adapter_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get adapter calls"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    calls = await am.get_call_history(adapter_id, limit=limit, offset=offset)
    return {
        "calls": [{"id": c.id, "model": c.model, "status": c.status, "duration_ms": c.duration_ms, "tokens": c.tokens, "timestamp": c.timestamp.isoformat() if c.timestamp else None} for c in calls],
        "total": len(calls),
    }


@router.get("/adapters/{adapter_id}/model-distribution")
async def get_model_distribution(adapter_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get model distribution"""
    am = _am(rt)
    if not am:
        raise HTTPException(status_code=503, detail="AdapterManager not initialized")
    distribution = await am.get_model_distribution(adapter_id)
    return {"distribution": distribution}

