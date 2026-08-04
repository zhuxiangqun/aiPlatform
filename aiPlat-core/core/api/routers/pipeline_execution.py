"""
Core pipeline execution endpoints.

POST  /api/core/pipeline/run          → 202 Accepted + run_id
GET   /api/core/pipeline/{project_id}/state  → aggregated state
POST  /api/core/pipeline/{project_id}/cancel → cancel a running pipeline
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from core.harness.execution.pipeline_run_store import get_pipeline_run_store

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_log = logging.getLogger("aiplat.pipeline.api")


@router.post("/run")
async def pipeline_run(request: Request) -> Dict[str, Any]:
    """Trigger a pipeline run. Returns 202 with run_id immediately.

    The pipeline executes asynchronously — this endpoint only enqueues.
    Poll GET /{project_id}/state for progress.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    project_id = str(body.get("project_id", "") or "")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    store = get_pipeline_run_store()

    # Check for existing executing run
    existing = store.get_run_by_project(project_id)
    if existing and existing.get("phase") == "executing":
        return {
            "status": "conflict",
            "run_id": existing["run_id"],
            "detail": "Pipeline already running for this project",
        }

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    config = body.get("config", {})

    store.create_run(
        run_id=run_id,
        project_id=project_id,
        total_stages=config.get("total_stages", 0),
        tokens_budget=config.get("tokens_budget", 0),
    )

    # Enqueue pipeline execution via background task
    from api.deps import get_stage_runner  # noqa: deferred import

    async def _execute_pipeline():
        try:
            from core.harness.execution.pipeline_engine import PipelineEngine, PipelineConfig
            from core.schemas_builder import PipelineStageConfig

            stages_raw = config.get("stages", [])
            stages = []
            for s in stages_raw:
                if isinstance(s, dict):
                    stages.append(PipelineStageConfig(**s))

            pipeline_config = PipelineConfig(
                stages=stages,
                max_tokens_per_run=config.get("tokens_budget", 100000),
                max_retry_attempts=3,
            )
            engine = PipelineEngine(config=pipeline_config)
            state: Dict[str, Any] = {
                "session_id": run_id,
                "phase": "executing",
                "iteration": 1,
                "max_iterations": 3,
                "tokens_used": 0,
                "tokens_budget": config.get("tokens_budget", 100000),
                "output_dir": config.get("output_dir", ""),
                "description": config.get("description", ""),
                "pass_rate": 0.0,
                "issues": {},
                "context": {},
            }

            # Run pipeline — write progress via PipelineRunStore
            result = await engine._run_stages_from(0, state)

            # Save final state
            phase = result.get("phase", "done")
            error = result.get("error", "")
            store.update_run_phase(run_id, phase, error=str(error)[:500])
            store.update_run_progress(
                run_id,
                current_stage_idx=result.get("_current_stage_idx", 0),
                pass_rate=result.get("pass_rate", 0.0),
            )

            _log.info("Pipeline %s completed: phase=%s", run_id, phase)
        except Exception as e:
            _log.error("Pipeline %s failed: %s", run_id, str(e)[:500], exc_info=True)
            store.update_run_phase(run_id, "failed", str(e)[:500])

    asyncio.create_task(_execute_pipeline())

    return {"status": "accepted", "run_id": run_id}


@router.get("/{project_id}/state")
async def pipeline_state(project_id: str) -> Dict[str, Any]:
    """Return aggregated pipeline state for frontend polling."""
    store = get_pipeline_run_store()
    state = store.get_full_state(project_id)

    if state.get("phase") == "idle":
        return {"project_id": project_id, "phase": "idle", "state": {}}

    return {
        "project_id": project_id,
        "phase": state.get("phase", "idle"),
        "state": state,
    }


@router.post("/{project_id}/cancel")
async def pipeline_cancel(project_id: str) -> Dict[str, Any]:
    """Cancel a running pipeline."""
    store = get_pipeline_run_store()
    run = store.get_run_by_project(project_id)

    if not run:
        return {"status": "not_found", "detail": "No pipeline for this project"}

    if run.get("phase") != "executing":
        return {"status": "conflict", "detail": f"Pipeline is {run.get('phase')}"}

    store.update_run_phase(run["run_id"], "cancelled")
    return {"status": "ok", "detail": "Pipeline cancelled"}
