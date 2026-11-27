"""FDE 交付计划 API — 需求→实施计划生成与进度刷新（走 CoreFacade）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from apps.fde.api.schemas import (
    DeliveryPlanGenerateRequest,
    DeliveryPlanRefreshRequest,
    DeliveryPlanStepPatchRequest,
    FdeItemResponse,
)

router = APIRouter(tags=["fde-delivery-plan"])


def _snapshot_dict(snap: Any) -> Dict[str, bool]:
    """将 Pydantic snapshot 转为 dict。

    Args:
        snap: DeliveryPlanPipelineSnapshot 或 None。
    """
    if snap is None:
        return {}
    if hasattr(snap, "model_dump"):
        return dict(snap.model_dump())
    if isinstance(snap, dict):
        return snap
    return {}


@router.post("/delivery-plan/generate", response_model=FdeItemResponse)
async def generate_delivery_plan(req: DeliveryPlanGenerateRequest) -> FdeItemResponse:
    """根据客户需求生成 FDE 实施计划（骨架+LLM 填空；LLM 失败仍返回骨架）。

    Args:
        req: 生成请求。
    """
    from core.api.core_facade import generate_fde_delivery_plan

    ns = (req.customer_namespace or "").strip()
    text = (req.requirement_text or "").strip()
    if not ns:
        raise HTTPException(status_code=400, detail="customer_namespace is required")
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="requirement_text too short (min 20 chars)")
    try:
        plan = await generate_fde_delivery_plan(
            customer_namespace=ns,
            requirement_text=text,
            title=(req.title or "").strip(),
            pipeline_snapshot=_snapshot_dict(req.pipeline_snapshot),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"generate failed: {e}") from e
    return FdeItemResponse(data=plan if isinstance(plan, dict) else {"plan": plan})


@router.get("/delivery-plan", response_model=FdeItemResponse)
async def get_delivery_plan(
    customer_namespace: str = Query(...),
    refresh: bool = Query(False),
) -> FdeItemResponse:
    """读取已存交付计划；无计划时 data 为空对象且含 null 标记。

    Args:
        customer_namespace: 客户命名空间。
        refresh: 为 True 时仅重算已存计划进度（无 snapshot 则保持原 progress）。
    """
    from core.api.core_facade import get_fde_delivery_plan

    ns = (customer_namespace or "").strip()
    if not ns:
        raise HTTPException(status_code=400, detail="customer_namespace is required")
    try:
        plan = get_fde_delivery_plan(ns, pipeline_snapshot=None, refresh=refresh)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if plan is None:
        return FdeItemResponse(data={"plan": None})
    return FdeItemResponse(data=plan)


@router.post("/delivery-plan/refresh", response_model=FdeItemResponse)
async def refresh_delivery_plan(req: DeliveryPlanRefreshRequest) -> FdeItemResponse:
    """按 pipeline_snapshot 重算步骤状态与完成度并落盘。

    Args:
        req: 刷新请求。
    """
    from core.api.core_facade import get_fde_delivery_plan

    ns = (req.customer_namespace or "").strip()
    if not ns:
        raise HTTPException(status_code=400, detail="customer_namespace is required")
    plan = get_fde_delivery_plan(
        ns,
        pipeline_snapshot=_snapshot_dict(req.pipeline_snapshot),
        refresh=True,
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="delivery plan not found")
    return FdeItemResponse(data=plan)


@router.patch("/delivery-plan/steps/{step_id}", response_model=FdeItemResponse)
async def patch_delivery_plan_step(
    step_id: str,
    req: DeliveryPlanStepPatchRequest,
) -> FdeItemResponse:
    """人工勾选无 auto_check 的步骤；auto 步骤返回 422。

    Args:
        step_id: 步骤 id。
        req: 勾选请求。
    """
    from core.api.core_facade import patch_fde_delivery_plan_step

    ns = (req.customer_namespace or "").strip()
    sid = (step_id or "").strip()
    if not ns:
        raise HTTPException(status_code=400, detail="customer_namespace is required")
    if not sid:
        raise HTTPException(status_code=400, detail="step_id is required")
    try:
        plan = patch_fde_delivery_plan_step(
            customer_namespace=ns,
            step_id=sid,
            manual_done=bool(req.manual_done),
            pipeline_snapshot=_snapshot_dict(req.pipeline_snapshot),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="delivery plan not found") from None
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return FdeItemResponse(data=plan)
