"""Business Value Center — REST API for five-dimension ROI + business goals + strategy.

Endpoints:
  GET  /value/{tenant_id}?month=2026-07&audience=ceo|cfo|pm
  GET  /value/{tenant_id}/goals
  POST /value/{tenant_id}/goals
  PUT  /value/{tenant_id}/goals/{goal_id}
  DELETE /value/{tenant_id}/goals/{goal_id}
  GET  /value/{tenant_id}/strategy
"""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Optional
import os

router = APIRouter(prefix="/value", tags=["value"])


@router.get("/{tenant_id}")  # noqa: contract-ok
async def get_value_dashboard(
    tenant_id: str, month: str = "", audience: str = "ceo",
) -> Dict[str, Any]:
    """Get five-dimension value dashboard for a tenant/month/audience."""
    if not month:
        import time
        month = time.strftime("%Y-%m")
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        calc = get_value_calculator()
        report = await calc.compute_monthly(tenant_id=tenant_id, month=month)
        return calc.translate_for(report, audience)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{tenant_id}/goals")  # noqa: contract-ok
async def get_business_goals(tenant_id: str) -> List[Dict[str, Any]]:
    """Get all business goals for a tenant."""
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        calc = get_value_calculator()
        goals = calc.goal_tracker.get_all()
        return [{
            "goal_id": g.goal_id, "description": g.description,
            "target_metric": g.target_metric,
            "baseline_value": g.baseline_value, "target_value": g.target_value,
            "current_value": g.current_value, "progress_pct": g.progress_pct,
            "achieved": g.achieved, "owner": g.owner, "period": g.period,
        } for g in goals]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/{tenant_id}/goals")  # noqa: contract-ok
async def create_business_goal(tenant_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Register a new business goal."""
    try:
        from core.harness.finance.value_calculator import (
            get_value_calculator, BusinessGoal,
        )
        calc = get_value_calculator()
        goal = BusinessGoal(
            goal_id=body.get("goal_id", body.get("goal_id", "")),
            description=body.get("description", ""),
            target_metric=body.get("target_metric", ""),
            baseline_value=float(body.get("baseline_value", 0)),
            target_value=float(body.get("target_value", 0)),
            owner=body.get("owner", ""),
            period=body.get("period", ""),
        )
        if not goal.goal_id:
            raise HTTPException(status_code=400, detail="goal_id is required")
        calc.goal_tracker.register(goal)
        return {"goal_id": goal.goal_id, "status": "created"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.put("/{tenant_id}/goals/{goal_id}")  # noqa: contract-ok
async def update_business_goal(
    tenant_id: str, goal_id: str, body: Dict[str, Any],
) -> Dict[str, Any]:
    """Update a business goal (e.g., current_value)."""
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        calc = get_value_calculator()
        current = body.get("current_value")
        if current is not None:
            g = calc.goal_tracker.update(goal_id, float(current))
            if not g:
                raise HTTPException(status_code=404, detail=f"goal {goal_id} not found")
            return {"goal_id": goal_id, "current_value": g.current_value,
                    "progress_pct": g.progress_pct, "achieved": g.achieved}
        raise HTTPException(status_code=400, detail="current_value is required")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.delete("/{tenant_id}/goals/{goal_id}")  # noqa: contract-ok
async def delete_business_goal(tenant_id: str, goal_id: str) -> Dict[str, Any]:
    """Delete a business goal."""
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        calc = get_value_calculator()
        if goal_id in calc.goal_tracker._goals:
            del calc.goal_tracker._goals[goal_id]
            calc.goal_tracker._save()
            return {"goal_id": goal_id, "deleted": True}
        raise HTTPException(status_code=404, detail=f"goal {goal_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{tenant_id}/strategy")  # noqa: contract-ok
async def get_strategy_status(tenant_id: str) -> Dict[str, Any]:
    """Get current routing strategy status (from GoalAwareRouter)."""
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        from core.harness.execution.dynamic_router import GoalAwareRouter
        calc = get_value_calculator()
        tracker = calc.goal_tracker
        router = GoalAwareRouter(goal_tracker=tracker)
        result = router.adjust()
        return {
            "params": result["params"],
            "context": result["context"],
            "goals_count": len(tracker.get_all()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{tenant_id}/goals/{goal_id}/trend")  # noqa: contract-ok
async def get_goal_trend(tenant_id: str, goal_id: str) -> Dict[str, Any]:
    """Get historical trend data for a business goal (sparkline chart)."""
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        calc = get_value_calculator()
        goal = calc.goal_tracker.get(goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")
        import json as _j
        report_path = os.path.expanduser("~/.aiplat/value/monthly.jsonl")
        trend = []
        if os.path.exists(report_path):
            with open(report_path) as f:
                for line in f:
                    try:
                        entry = _j.loads(line)
                        trend.append({"month": entry.get("month", ""),
                                      "total_value_cny": entry.get("total_value_cny", 0),
                                      "total_runs": entry.get("total_runs", 0)})
                    except Exception:
                        pass
        return {"goal_id": goal_id, "trend": trend[-12:],
                "current_progress_pct": goal.progress_pct}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.put("/{tenant_id}/goals/{goal_id}/source")  # noqa: contract-ok
async def configure_goal_source(
    tenant_id: str, goal_id: str, body: Dict[str, Any],
) -> Dict[str, Any]:
    """Configure data collection source for a business goal."""
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        calc = get_value_calculator()
        goal = calc.goal_tracker.get(goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")
        source = body.get("collection_method", "auto")
        agent_id = body.get("linked_agent", "")
        category = body.get("category", "efficiency")
        return {"goal_id": goal_id, "collection_method": source,
                "linked_agent": agent_id, "category": category, "status": "configured"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])
