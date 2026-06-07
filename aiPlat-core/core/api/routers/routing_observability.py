from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.integration import KernelRuntime
RuntimeDep = Optional[KernelRuntime]
from core.observability.routing_service import (
    routing_explain_events,
    routing_metric_tags,
    routing_metrics,
    routing_replay,
    skill_routing_funnel,
)


router = APIRouter()

def _store():
    rt = get_kernel_runtime()
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/workspace/skills/observability/routing-funnel")
async def workspace_routing_funnel(
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 20000,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await skill_routing_funnel(
                store=_store(),
                tenant_id=tenant_id,
                since_hours=since_hours,
                limit=limit,
                coding_policy_profile=coding_policy_profile,
            )
        ),
    }


@router.get("/workspace/skills/observability/routing-explain")
async def workspace_routing_explain(
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 500,
    skill_id: Optional[str] = None,
    selected_kind: Optional[str] = None,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await routing_explain_events(
                store=_store(),
                tenant_id=tenant_id,
                since_hours=since_hours,
                limit=limit,
                skill_id=skill_id,
                selected_kind=selected_kind,
                coding_policy_profile=coding_policy_profile,
            )
        ),
    }


@router.get("/workspace/skills/observability/routing-replay")
async def workspace_routing_replay(
    routing_decision_id: str,
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 2000,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await routing_replay(
                store=_store(),
                tenant_id=tenant_id,
                routing_decision_id=routing_decision_id,
                since_hours=since_hours,
                limit=limit,
                coding_policy_profile=coding_policy_profile,
            )
        ),
    }


@router.get("/workspace/skills/observability/routing-metrics")
async def workspace_routing_metrics(
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    bucket_minutes: int = 60,
    skill_id: Optional[str] = None,
    coding_policy_profile: Optional[str] = None,
    limit: int = 20000,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await routing_metrics(
                store=_store(),
                tenant_id=tenant_id,
                since_hours=since_hours,
                bucket_minutes=bucket_minutes,
                skill_id=skill_id,
                scope="workspace",
                coding_policy_profile=coding_policy_profile,
                limit=limit,
            )
        ),
    }


@router.get("/workspace/skills/observability/routing-metrics/tags")
async def workspace_routing_metric_tags() -> Dict[str, Any]:
    return {"status": "ok", **routing_metric_tags()}


@router.get("/skills/observability/routing-funnel")
async def engine_routing_funnel(
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 20000,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await skill_routing_funnel(
                store=_store(),
                tenant_id=tenant_id,
                since_hours=since_hours,
                limit=limit,
                coding_policy_profile=coding_policy_profile,
            )
        ),
    }


@router.get("/skills/observability/routing-explain")
async def engine_routing_explain(
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 500,
    skill_id: Optional[str] = None,
    selected_kind: Optional[str] = None,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await routing_explain_events(
                store=_store(),
                tenant_id=tenant_id,
                since_hours=since_hours,
                limit=limit,
                skill_id=skill_id,
                selected_kind=selected_kind,
                coding_policy_profile=coding_policy_profile,
            )
        ),
    }


@router.get("/skills/observability/routing-replay")
async def engine_routing_replay(
    routing_decision_id: str,
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 2000,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await routing_replay(
                store=_store(),
                tenant_id=tenant_id,
                routing_decision_id=routing_decision_id,
                since_hours=since_hours,
                limit=limit,
                coding_policy_profile=coding_policy_profile,
            )
        ),
    }


@router.get("/skills/observability/routing-metrics")
async def engine_routing_metrics(
    tenant_id: Optional[str] = None,
    since_hours: int = 24,
    bucket_minutes: int = 60,
    skill_id: Optional[str] = None,
    coding_policy_profile: Optional[str] = None,
    limit: int = 20000,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **(
            await routing_metrics(
                store=_store(),
                tenant_id=tenant_id,
                since_hours=since_hours,
                bucket_minutes=bucket_minutes,
                skill_id=skill_id,
                scope="engine",
                coding_policy_profile=coding_policy_profile,
                limit=limit,
            )
        ),
    }


@router.post("/routing/learn")
async def apply_routing_learning(rt: RuntimeDep = None):
    """
    Analyze routing strict_eval events and adjust per-skill routing weights.
    
    Call periodically to let the system learn which skills are correctly matched.
    Returns the adjusted weights.
    """
    try:
        from core.harness.routing.skill_routing import apply_learned_weights, get_all_weights
        result = apply_learned_weights()
        result["weights"] = get_all_weights()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing learning failed: {e}")


@router.get("/skills/observability/routing-metrics/tags")
async def engine_routing_metric_tags() -> Dict[str, Any]:
    return {"status": "ok", **routing_metric_tags()}
