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

# ── v3.1: per-project building flag prevents duplicate concurrent runs ──
_building_flags: Dict[str, bool] = {}


async def cleanup_orphaned_pipelines():
    """Startup: mark only truly orphaned (executing) runs as failed.
    
    Paused/HITL pipelines are legitimate — user was about to approve/reject.
    They should survive restart and be re-registered for HITL continuation.
    """
    try:
        store = get_pipeline_run_store()
        conn = store._get_conn()
        # Only kill pipelines that were mid-execution (no HITL guarding them)
        conn.execute(
            "UPDATE pipeline_runs SET phase='failed', error_message='系统重启, 流水线中断' "
            "WHERE phase = 'executing'"
        )
        count = conn.total_changes
        conn.commit()
        if count:
            _log.warning("Orphan cleanup: %d executing pipeline(s) marked as failed", count)
        else:
            _log.info("Orphan cleanup: no executing pipelines found")
    except Exception:
        _log.warning("Orphan cleanup failed", exc_info=True)


def _make_store_callback(run_id: str, store):
    """Create a persist_callback that writes progress + artifacts to PipelineRunStore."""

    def _cb(state: dict):
        try:
            _phase = state.get("phase", "executing")
            store.update_run_progress(
                run_id,
                current_stage_idx=state.get("_current_stage_idx", 0),
                pass_rate=state.get("pass_rate", 0.0),
            )
            # ── v3.1: sync phase + HITL fields ──
            store.update_run_phase(run_id, _phase)
            _hitl_id = state.get("_hitl_stage_id", "")
            if _hitl_id:
                store.update_hitl_fields(
                    run_id,
                    hitl_stage_id=_hitl_id,
                    hitl_phase_name=state.get("_hitl_phase_name", "review"),
                    hitl_output_artifact=state.get("_hitl_output_artifact", ""),
                )
            else:
                store.clear_hitl_fields(run_id)

            # Write per-artifact progress (state keys with raw_output are artifacts)
            for key, val in state.items():
                if isinstance(val, dict) and val.get("raw_output"):
                    stage_id = key.replace("_", "-")  # prd, architecture, etc → stage ids
                    store.upsert_stage(
                        run_id, stage_id,
                        status="completed",
                        artifact_key=key,
                        artifact_output=str(val.get("raw_output", ""))[:50000],
                        elapsed_sec=float(val.get("elapsed_sec", 0) or 0),
                    )

            # Write health reports (_health_report_{stage_id} keys)
            for key, val in state.items():
                if key.startswith("_health_report_") and isinstance(val, dict):
                    store.upsert_stage(
                        run_id, key,
                        status="completed",
                        artifact_key=key,
                        artifact_output="",
                        elapsed_sec=0,
                        progress=val,
                    )

            # Write _progress as stage progress
            progress = state.get("_progress")
            if progress and isinstance(progress, dict):
                stage_id = progress.get("stage", "current")
                store.upsert_stage(
                    run_id, stage_id,
                    status=progress.get("status", "running"),
                    progress=progress,
                )

        except Exception:
            _log.debug("persist callback failed", exc_info=True)

    return _cb


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

    # ── v3.1: prevent duplicate concurrent runs ──
    if _building_flags.get(project_id):
        return {"status": "conflict", "detail": "已有正在执行的流水线, 请稍后重试"}
    _building_flags[project_id] = True

    store = get_pipeline_run_store()

    # Check for existing executing run
    existing = store.get_run_by_project(project_id)
    if existing and existing.get("phase") == "executing":
        _building_flags.pop(project_id, None)
        return {
            "status": "conflict",
            "run_id": existing["run_id"],
            "detail": "Pipeline already running for this project",
        }

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    config = body.get("config", {})
    stages_raw = config.get("stages", [])

    store.create_run(
        run_id=run_id,
        project_id=project_id,
        total_stages=len(stages_raw),
        tokens_budget=config.get("tokens_budget", 0),
    )

    # Pre-create stage records
    for i, s in enumerate(stages_raw[:]):
        if isinstance(s, dict):
            store.upsert_stage(
                run_id, s.get("id", f"stage_{i}"),
                stage_idx=i,
                agent_id=s.get("agent_id", ""),
                skill_name=s.get("skill_name", ""),
                status="pending",
            )

    # Enqueue pipeline execution via background task
    _persist = _make_store_callback(run_id, store)

    async def _execute_pipeline():
        try:
            from core.harness.execution.pipeline_engine import PipelineEngine, PipelineConfig
            from core.schemas_builder import PipelineStageConfig
            from core.harness.execution.team_planner import _ensure_capability_profile
            from core.harness.utils.model_injection import best_model_for_purpose

            stages = []
            for s in stages_raw:
                if isinstance(s, dict):
                    _ensure_capability_profile(s)  # guarantee all core capabilities
                    stages.append(PipelineStageConfig(**s))

            pipeline_config = PipelineConfig(
                stages=stages,
                max_tokens_per_run=config.get("tokens_budget", 100000),
                max_retry_attempts=3,
            )
            engine = PipelineEngine(
                config=pipeline_config,
                model=best_model_for_purpose("chat"),
                persist_callback=_persist,
            )
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

            # ── v3.1: Event-driven engine — run() handles full lifecycle incl HITL ──
            await engine.run(project_id, state)
        except asyncio.CancelledError:
            _building_flags.pop(project_id, None)
            raise
        except Exception as e:
            _log.error("Pipeline %s failed: %s", run_id, str(e)[:500], exc_info=True)
            store.update_run_phase(run_id, "failed", str(e)[:500])
        finally:
            _building_flags.pop(project_id, None)

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


@router.post("/{project_id}/hitl-resolve")
async def pipeline_hitl_resolve(project_id: str, request: Request) -> Dict[str, Any]:
    """v3.1: Resolve a HITL pause — approve or reject from Platform."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = str(body.get("action", "approve")).lower()
    feedback = str(body.get("feedback", ""))

    from core.harness.execution.pipeline_engine import get_running_pipeline

    engine = get_running_pipeline(project_id)
    if not engine:
        raise HTTPException(status_code=404, detail="No active pipeline for this project")

    if action == "approve":
        engine.approve(feedback)
        return {"status": "resolved", "project_id": project_id, "action": "approved"}
    elif action == "reject":
        engine.reject(feedback)
        return {"status": "resolved", "project_id": project_id, "action": "rejected"}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


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
