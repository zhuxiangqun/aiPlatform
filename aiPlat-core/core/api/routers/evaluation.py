u"""Agent Runtime Evaluation API — eval set management + run + results.

Endpoints:
  GET    /evaluation/overview            — global dashboard
  GET    /evaluation/sets                — list eval sets
  POST   /evaluation/sets                — create eval set
  GET    /evaluation/sets/{id}           — get eval set
  PUT    /evaluation/sets/{id}           — update eval set
  DELETE /evaluation/sets/{id}           — delete eval set
  POST   /evaluation/sets/{id}/run       — run evaluation
  GET    /evaluation/sets/{id}/results   — get results
  GET    /evaluation/agents/{id}/score   — agent runtime score
  GET    /evaluation/agents/{id}/history — agent eval history
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel


router = APIRouter(prefix="/evaluation", tags=["evaluation"])


# ── Request / Response Models ────────────────────────────────────────────────

class EvalTaskCreate(BaseModel):
    task_id: str
    agent_id: str
    user_input: str
    category: str = "normal"
    expected_tools: List[str] = []
    forbidden_tools: List[str] = []
    expected_steps: List[int] = []
    success_criteria: Dict[str, Any] = {}
    risk_level: str = "low"


class EvalSetCreate(BaseModel):
    set_id: str
    category: str = "custom"
    description: str = ""
    tasks: List[EvalTaskCreate] = []


class EvalSetUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    tasks: Optional[List[EvalTaskCreate]] = None


class EvalRunRequest(BaseModel):
    max_tasks: int = 0
    dry_run: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _results_dir() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    d = Path(home) / "eval_results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_result(agent_id: str, result: Dict[str, Any]) -> str:
    ts = int(time.time())
    path = _results_dir() / f"{agent_id}_{ts}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _load_results(agent_id: str = "") -> List[Dict[str, Any]]:
    results = []
    pattern = f"{agent_id}_*.json" if agent_id else "*.json"
    for fp in sorted(_results_dir().glob(pattern), reverse=True):
        try:
            results.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


async def _load_results_async(agent_id: str = "") -> List[Dict[str, Any]]:
    """Async wrapper to avoid blocking the event loop with file I/O."""
    import asyncio
    return await asyncio.to_thread(_load_results, agent_id)


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_evaluation_overview():
    u"""Global evaluation dashboard — scores for all evaluated agents."""
    from core.harness.evaluation.eval_runner import list_eval_sets

    eval_sets = list_eval_sets()
    all_results = await _load_results_async()

    # Aggregate by agent
    agent_scores: Dict[str, List[float]] = {}
    for r in all_results:
        aid = r.get("agent_id", "unknown")
        score = r.get("composite_score", 0)
        agent_scores.setdefault(aid, []).append(score)

    agents = []
    for aid, scores in sorted(agent_scores.items()):
        latest = scores[0] if scores else 0
        avg = sum(scores) / len(scores) if scores else 0
        trend = "up" if len(scores) >= 2 and scores[0] > scores[-1] else "down" if len(scores) >= 2 else "stable"
        agents.append({
            "agent_id": aid,
            "latest_score": round(latest, 1),
            "avg_score": round(avg, 1),
            "evals_count": len(scores),
            "trend": trend,
        })

    return {
        "total_evals": len(all_results),
        "eval_sets": len(eval_sets),
        "agents_evaluated": len(agent_scores),
        "agents": agents,
    }


# ── Eval Sets CRUD ────────────────────────────────────────────────────────────

@router.get("/sets")
async def list_eval_sets_api():
    u"""List all eval sets (built-in + custom)."""
    from core.harness.evaluation.eval_runner import list_eval_sets
    return {"items": list_eval_sets()}


@router.post("/sets")
async def create_eval_set_api(req: EvalSetCreate):
    u"""Create or overwrite an eval set."""
    from core.harness.evaluation.eval_runner import save_eval_set
    from core.harness.evaluation.eval_types import EvalSet, EvalTask

    evalset = EvalSet(
        set_id=req.set_id,
        category=req.category,
        description=req.description,
        tasks=[EvalTask(**t.model_dump()) for t in req.tasks],
    )
    path = save_eval_set(evalset)
    return {"set_id": req.set_id, "tasks": len(req.tasks), "saved_to": path}


@router.get("/sets/{set_id}")
async def get_eval_set_api(set_id: str):
    u"""Get an eval set by ID."""
    from core.harness.evaluation.eval_runner import load_eval_set
    s = load_eval_set(set_id)
    if not s:
        raise HTTPException(404, f"Eval set '{set_id}' not found")
    return {
        "set_id": s.set_id, "category": s.category, "description": s.description,
        "tasks": [{"task_id": t.task_id, "agent_id": t.agent_id, "user_input": t.user_input,
                   "category": t.category, "expected_tools": t.expected_tools,
                   "forbidden_tools": t.forbidden_tools, "risk_level": t.risk_level,
                   "success_criteria": t.success_criteria} for t in s.tasks],
    }


@router.put("/sets/{set_id}")
async def update_eval_set_api(set_id: str, req: EvalSetUpdate):
    u"""Update an eval set's description/tasks."""
    from core.harness.evaluation.eval_runner import load_eval_set, save_eval_set
    from core.harness.evaluation.eval_types import EvalTask

    s = load_eval_set(set_id)
    if not s:
        raise HTTPException(404, f"Eval set '{set_id}' not found")
    if req.category is not None:
        s.category = req.category
    if req.description is not None:
        s.description = req.description
    if req.tasks is not None:
        s.tasks = [EvalTask(**t.model_dump()) for t in req.tasks]
    path = save_eval_set(s)
    return {"set_id": set_id, "tasks": len(s.tasks), "saved_to": path}


@router.delete("/sets/{set_id}")
async def delete_eval_set_api(set_id: str):
    u"""Delete an eval set."""
    from core.harness.evaluation.eval_runner import delete_eval_set
    ok = delete_eval_set(set_id)
    if not ok:
        raise HTTPException(404, f"Eval set '{set_id}' not found")
    return {"status": "ok"}


# ── Run Evaluation ────────────────────────────────────────────────────────────

@router.post("/sets/{set_id}/run")
async def run_eval_set_api(set_id: str, req: EvalRunRequest = EvalRunRequest()):
    u"""Run all tasks in an eval set against agents. Returns composite result.

    This is a potentially long-running operation. Set dry_run=True to validate
    without executing.
    """
    from core.harness.evaluation.eval_runner import load_eval_set, EvalRunner
    from core.harness.evaluation.eval_metrics import EvalMetricsEngine

    evalset = load_eval_set(set_id)
    if not evalset:
        raise HTTPException(404, f"Eval set '{set_id}' not found")

    runner = EvalRunner()
    result = await runner.run_eval_set(
        evalset,
        max_tasks=req.max_tasks,
        dry_run=req.dry_run,
    )

    # Persist result
    data = {
        "agent_id": result.agent_id,
        "eval_set_id": result.eval_set_id,
        "eval_time": result.eval_time,
        "total_tasks": result.total_tasks,
        "composite_score": round(result.composite_score, 1),
        "grade": result.grade,
        "task_completion": {
            "level": result.task_completion.level.value if result.task_completion else "unknown",
            "score": result.task_completion.score if result.task_completion else 0,
            "complete": result.task_completion.complete_count if result.task_completion else 0,
            "partial": result.task_completion.partial_count if result.task_completion else 0,
            "correct_failure": result.task_completion.correct_failure_count if result.task_completion else 0,
            "error_failure": result.task_completion.error_failure_count if result.task_completion else 0,
            "reliability": round(result.task_completion.reliability_rate * 100, 1) if result.task_completion else 0,
        },
        "tool_quality": {
            "overall": round(result.tool_quality.overall_score * 100, 1) if result.tool_quality else 0,
            "selection_rate": round(result.tool_quality.selection_rate * 100, 1) if result.tool_quality else 0,
            "param_rate": round(result.tool_quality.param_rate * 100, 1) if result.tool_quality else 0,
            "violations": result.tool_quality.high_risk_violations if result.tool_quality else 0,
        },
        "step_efficiency": {
            "avg_steps": round(result.step_efficiency.avg_steps, 1) if result.step_efficiency else 0,
            "invalid_call_rate": round(result.step_efficiency.invalid_call_rate * 100, 1) if result.step_efficiency else 0,
            "repeat_call_rate": round(result.step_efficiency.repeat_call_rate * 100, 1) if result.step_efficiency else 0,
            "score": round(result.step_efficiency.overall_score * 100, 1) if result.step_efficiency else 0,
        },
        "error_recovery": {
            "rate": round(result.error_recovery.recovery_rate * 100, 1) if result.error_recovery else 0,
            "total_failures": result.error_recovery.total_failures if result.error_recovery else 0,
            "correct_recoveries": result.error_recovery.correct_recoveries if result.error_recovery else 0,
        },
        "safety": {
            "score": round(result.safety.overall_score * 100, 1) if result.safety else 0,
            "violations": result.safety.high_risk_pre_confirm_violations if result.safety else 0,
            "bypass_attempts": result.safety.permission_bypass_attempts if result.safety else 0,
            "info_leaks": result.safety.sensitive_info_leaks if result.safety else 0,
        },
        "cost": {
            "tokens_per_task": result.cost.tokens_per_task if result.cost else 0,
            "calls_per_task": round(result.cost.calls_per_task, 1) if result.cost else 0,
            "avg_duration_ms": round(result.cost.avg_duration_ms, 0) if result.cost else 0,
        },
        "task_results": [
            {
                "task_id": tr.task_id, "agent_id": tr.agent_id, "run_id": tr.run_id,
                "level": tr.level.value, "reasoning": tr.reasoning,
                "steps": tr.steps, "duration_ms": tr.duration_ms,
            }
            for tr in result.task_results
        ],
    }
    _save_result(result.agent_id, data)

    return data


@router.get("/sets/{set_id}/results")
async def get_eval_set_results(set_id: str):
    u"""Get evaluation results for a specific eval set."""
    all_results = await _load_results_async()
    matches = [r for r in all_results if r.get("eval_set_id") == set_id]
    return {"set_id": set_id, "results": matches, "count": len(matches)}


# ── Agent Scores ──────────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/score")
async def get_agent_eval_score(agent_id: str):
    u"""Get the latest runtime evaluation score with full 6-dim metrics."""
    results = await _load_results_async(agent_id)
    if not results:
        return {"agent_id": agent_id, "score": None, "message": "No evaluation data available"}
    latest = results[0]
    return {
        "agent_id": agent_id,
        "latest_score": latest.get("composite_score", 0),
        "grade": latest.get("grade", "?"),
        "eval_time": latest.get("eval_time", 0),
        "total_evals": len(results),
        "dimensions": {
            "task_completion": latest.get("task_completion", {}),
            "tool_quality": latest.get("tool_quality", {}),
            "step_efficiency": latest.get("step_efficiency", {}),
            "error_recovery": latest.get("error_recovery", {}),
            "safety": latest.get("safety", {}),
            "cost": latest.get("cost", {}),
        },
    }


@router.get("/agents/{agent_id}/history")
async def get_agent_eval_history(agent_id: str, limit: int = Query(10, ge=1, le=100)):
    u"""Get evaluation score history for an agent (for trend charts)."""
    results = (await _load_results_async(agent_id))[:limit]
    history = []
    for r in results:
        history.append({
            "eval_time": r.get("eval_time", 0),
            "composite_score": r.get("composite_score", 0),
            "grade": r.get("grade", "?"),
            "eval_set_id": r.get("eval_set_id", ""),
            "total_tasks": r.get("total_tasks", 0),
        })
    return {"agent_id": agent_id, "history": history, "count": len(history)}
