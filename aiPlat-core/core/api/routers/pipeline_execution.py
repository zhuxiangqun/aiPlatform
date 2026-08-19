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

from fastapi import APIRouter, Body, HTTPException, Request

from core.api.core_facade import get_pipeline_run_store  # P0-A2: 经 CoreFacade

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_log = logging.getLogger("aiplat.pipeline.api")

# ── v3.1: per-project building flag prevents duplicate concurrent runs ──
_building_flags: Dict[str, bool] = {}


async def cleanup_orphaned_pipelines():
    """Startup: mark executing runs as failed, recover paused ones from DB.

    Paused/HITL pipelines are legitimate — user was about to approve/reject.
    They survive restart by rebuilding the PipelineEngine from saved state.
    """
    try:
        store = get_pipeline_run_store()
        conn = store._get_conn()

        # 1. Mark truly orphaned (executing) pipelines as failed
        conn.execute(
            "UPDATE pipeline_runs SET phase='failed', error_message='系统重启, 流水线中断' "
            "WHERE phase = 'executing'"
        )
        count = conn.total_changes
        if count:
            _log.warning("Orphan cleanup: %d executing pipeline(s) marked as failed", count)

        # 2. Recover paused (HITL) pipelines — only latest per project
        paused_runs = store.list_paused_runs()
        if paused_runs:
            # Deduplicate: keep only the most recent paused run per project
            latest_per_project: Dict[str, dict] = {}
            for run in paused_runs:
                pid = run["project_id"]
                if pid not in latest_per_project or run.get("updated_at", "") > latest_per_project[pid].get("updated_at", ""):
                    latest_per_project[pid] = run
            # Mark stale paused runs as failed
            for run in paused_runs:
                if run["run_id"] != latest_per_project.get(run["project_id"], {}).get("run_id"):
                    conn.execute(
                        "UPDATE pipeline_runs SET phase='expired', error_message='旧暂停记录已清理', "
                        "_hitl_stage_id='', _hitl_phase_name='', _hitl_output_artifact='' "
                        "WHERE run_id = ?", (run["run_id"],)
                    )
            to_recover = list(latest_per_project.values())
            _log.warning("Orphan recovery: %d paused pipeline(s) to rebuild (filtered from %d)",
                len(to_recover), len(paused_runs))
            from core.api.core_facade import (
                create_pipeline_engine, register_pipeline,
            )
            from core.schemas_builder import PipelineStageConfig, PipelineConfig  # P0-A2 回归修复: PipelineConfig 未 import 致 NameError
            from core.api.core_facade import best_model_for_purpose  # P0-A2: 经 CoreFacade

            for run in to_recover:
                run_id = run["run_id"]
                project_id = run["project_id"]
                try:
                    # Rebuild stage config from saved DB records
                    stage_rows = store.load_stages_config(run_id)
                    stages = []
                    for sr in stage_rows:
                        # Only stage-config rows (canvas_node_*) carry agent_id;
                        # artifact/progress rows (prd, test_cases, skill_name, …) are
                        # noise here and must be skipped, otherwise the stage list
                        # becomes misaligned with _current_stage_idx.
                        if not sr.get("agent_id"):
                            continue
                        input_arts = sr.get("input_artifacts", "")
                        inputs = [a.strip() for a in input_arts.split(",") if a.strip()] if input_arts else []
                        stage = PipelineStageConfig(
                            id=sr["stage_id"],
                            agent_id=sr.get("agent_id", ""),
                            agent_name=sr.get("agent_name", ""),
                            skill_name=sr.get("skill_name", ""),
                            output_artifact=sr.get("output_artifact", sr.get("artifact_key", "")),
                            hitl=bool(sr.get("hitl", False)),
                            hitl_phase=sr.get("hitl_phase", ""),
                            input_artifacts=inputs,
                        )
                        stages.append(stage)

                    if not stages:
                        _log.warning("Recovery: no stages for run %s, marking as failed", run_id)
                        conn.execute(
                            "UPDATE pipeline_runs SET phase='failed', error_message='恢复失败: 无阶段配置' "
                            "WHERE run_id = ?", (run_id,)
                        )
                        continue

                    pipeline_config = PipelineConfig(
                        stages=stages,
                        max_tokens_per_run=run.get("tokens_budget", 100000),
                        max_retry_attempts=3,
                    )

                    engine = create_pipeline_engine(
                        config=pipeline_config,
                        model=best_model_for_purpose("chat"),
                    )
                    engine._persist_callback = _make_store_callback(run_id, store)  # guard_undefined_names 修复

                    # Load saved state
                    saved_state = store.get_full_state_from_run_id(run_id)
                    engine._state = dict(saved_state)
                    engine._state.setdefault("phase", "paused")
                    engine._state.setdefault("project_id", project_id)
                    engine._state.setdefault("_current_stage_idx", run.get("current_stage_idx", 0))

                    # Register and resume in background
                    register_pipeline(project_id, engine)
                    asyncio.create_task(engine._resume_from_hitl())
                    _log.warning("Recovery: pipeline %s re-registered, HITL active", project_id)

                except Exception:
                    _log.warning("Recovery failed for run %s", run_id, exc_info=True)
                    conn.execute(
                        "UPDATE pipeline_runs SET phase='failed', error_message='恢复失败' "
                        "WHERE run_id = ?", (run_id,)
                    )

        else:
            _log.info("Orphan recovery: no paused pipelines found")

        conn.commit()
    except Exception:
        _log.warning("Orphan cleanup/recovery failed", exc_info=True)


def _make_store_callback(run_id: str, store):
    """Create a persist_callback that writes progress + artifacts to PipelineRunStore."""

    def _cb(state: dict):
        try:
            import json as _json
            _phase = state.get("phase", "executing")
            # P2-A1: append-only event log (dual-write, backward compatible)
            try:
                _evt_type = {
                    "done": "pipeline_finished",
                    "failed": "pipeline_failed",
                    "cancelled": "pipeline_cancelled",
                    "paused": "pipeline_paused",
                    "review": "pipeline_hitl",
                    "executing": "pipeline_progress",
                }.get(_phase, "pipeline_progress")
                store.append_run_event(
                    run_id, _evt_type,
                    stage_id=str(state.get("_current_stage_idx", "")),
                    payload={"phase": _phase,
                             "current_stage_idx": state.get("_current_stage_idx", 0),
                             "pass_rate": state.get("pass_rate", 0.0)},
                )
            except Exception as _e:  # noqa: BLE001
                import logging as _lg
                _lg.getLogger(__name__).debug("append_run_event failed: %s", _e)
            # v3.2: Atomic update — phase + HITL + progress in ONE SQL transaction
            store.atomic_update_phase_and_hitl(
                run_id,
                phase=_phase,
                current_stage_idx=state.get("_current_stage_idx", 0),
                pass_rate=state.get("pass_rate", 0.0),
                hitl_stage_id=state.get("_hitl_stage_id", ""),
                hitl_phase_name=state.get("_hitl_phase_name", "review"),
                hitl_output_artifact=state.get("_hitl_output_artifact", ""),
                error=state.get("error_message", state.get("error", "")),
                _progress_json=_json.dumps(state.get("_progress", {})),
                output_dir=state.get("output_dir", ""),
            )

            # Write per-artifact progress (state keys with raw_output are artifacts)
            import os as _osp
            _out_dir = state.get("output_dir", "")
            for key, val in state.items():
                if isinstance(val, dict) and val.get("raw_output"):
                    stage_id = key.replace("_", "-")  # prd, architecture, etc → stage ids
                    # Prefer filesystem path if artifact was written to disk
                    _fpath = _osp.path.join(_out_dir, f"{key}.json") if _out_dir else ""
                    artifact_out = _fpath if _fpath and _osp.path.isfile(_fpath) else str(val.get("raw_output", ""))[:50000]
                    store.upsert_stage(
                        run_id, stage_id,
                        status="completed",
                        artifact_key=key,
                        artifact_output=artifact_out,
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


def _reconstruct_engine(project_id: str, run_id: str, store, stages_raw=None):
    """Rebuild a PipelineEngine from saved DB state + optional fresh stage config.

    Used by stage-level operations (regenerate/rollback/resume) so the engine
    runs on Core (single authority) with the upstream artifacts preserved.

    When `stages_raw` is provided (fresh team config from platform), use it;
    otherwise fall back to the stage records saved in the store.
    """
    from core.api.core_facade import create_pipeline_engine
    from core.schemas_builder import PipelineStageConfig, PipelineConfig  # P0-A2 回归修复: PipelineConfig 未 import 致 NameError
    from core.api.core_facade import best_model_for_purpose  # P0-A2: 经 CoreFacade

    stages = []
    if stages_raw:
        from core.harness.execution.team_planner import _ensure_capability_profile
        for s in stages_raw:
            if isinstance(s, dict):
                _ensure_capability_profile(s)
                stages.append(PipelineStageConfig(**s))
    else:
        for sr in store.load_stages_config(run_id):
            input_arts = sr.get("input_artifacts", "")
            inputs = [a.strip() for a in input_arts.split(",") if a.strip()] if input_arts else []
            stages.append(PipelineStageConfig(
                id=sr["stage_id"],
                agent_id=sr.get("agent_id", ""),
                agent_name=sr.get("agent_name", ""),
                skill_name=sr.get("skill_name", ""),
                output_artifact=sr.get("output_artifact", sr.get("artifact_key", "")),
                hitl=bool(sr.get("hitl", False)),
                hitl_phase=sr.get("hitl_phase", ""),
                input_artifacts=inputs,
            ))

    if not stages:
        return None

    run = store.get_run(run_id) or {}
    pipeline_config = PipelineConfig(
        stages=stages,
        max_tokens_per_run=run.get("tokens_budget", 100000),
        max_retry_attempts=3,
    )
    engine = create_pipeline_engine(
        config=pipeline_config,
        model=best_model_for_purpose("chat"),
    )
    engine._persist_callback = _make_store_callback(run_id, store)  # P0-A2 回归修复: 经 CoreFacade 构造后挂回调
    saved_state = store.get_full_state_from_run_id(run_id)
    engine._state = dict(saved_state or {})
    return engine


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

    # Pre-create stage records with full config for restart recovery
    for i, s in enumerate(stages_raw[:]):
        if isinstance(s, dict):
            store.upsert_stage(
                run_id, s.get("id", f"stage_{i}"),
                stage_idx=i,
                agent_id=s.get("agent_id", ""),
                skill_name=s.get("skill_name", ""),
                status="pending",
                output_artifact=s.get("output_artifact", ""),
                hitl=bool(s.get("hitl", False)),
                hitl_phase=str(s.get("hitl_phase", "")),
                agent_name=str(s.get("agent_name", "")),
                input_artifacts=",".join(s.get("input_artifacts", []) or []),
            )

    # Enqueue pipeline execution via background task
    _persist = _make_store_callback(run_id, store)

    async def _execute_pipeline():
        try:
            from core.api.core_facade import create_pipeline_engine
            from core.schemas_builder import PipelineStageConfig, PipelineConfig  # P0-A2 回归修复: PipelineConfig 未 import 致 NameError
            from core.harness.execution.team_planner import _ensure_capability_profile
            from core.api.core_facade import best_model_for_purpose  # P0-A2: 经 CoreFacade

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
            engine = create_pipeline_engine(
                config=pipeline_config,
                model=best_model_for_purpose("chat"),
            )
            engine._persist_callback = _persist  # guard_undefined_names 修复
            state: Dict[str, Any] = {
                "session_id": run_id,
                "phase": "executing",
                "iteration": 1,
                "max_iterations": 3,
                "tokens_used": 0,
                "tokens_budget": config.get("tokens_budget", 100000),
                "output_dir": config.get("output_dir", ""),
                "description": config.get("description", ""),
                "app_name": config.get("app_name", ""),
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

    resp = {
        "project_id": project_id,
        "phase": state.get("phase", "idle"),
        "state": state,
    }
    # P2-A1 phase 2: attach the event-sourced (folded) view for audit cross-check
    try:
        run_id = state.get("run_id") or state.get("_run_id") or ""
        if run_id:
            derived = store.replay_run_events(run_id)
            if derived:
                resp["event_derived"] = derived
    except Exception as _e:  # noqa: BLE001
        import logging as _lg
        _lg.getLogger(__name__).debug("replay_run_events failed: %s", _e)
    return resp


@router.post("/{project_id}/hitl-resolve")
async def pipeline_hitl_resolve(project_id: str, request: Request) -> Dict[str, Any]:
    """v3.3: Resolve a HITL pause — approve or reject. Works cross-worker via DB fallback."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = str(body.get("action", "approve")).lower()
    feedback = str(body.get("feedback", ""))

    from core.api.core_facade import get_running_pipeline

    engine = get_running_pipeline(project_id)
    if engine:
        # Direct path: engine is on this worker
        if action == "approve":
            engine.approve(feedback)
        elif action == "reject":
            engine.reject(feedback)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
        return {"status": "resolved", "project_id": project_id, "action": action}

    # Cross-worker fallback: write action to DB — engine polls it
    store = get_pipeline_run_store()
    ok = store.write_hitl_action(project_id, action)
    if ok:
        return {"status": "resolved", "project_id": project_id, "action": action,
                "via": "db"}
    raise HTTPException(status_code=404, detail="No active paused pipeline for this project")


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


@router.post("/{project_id}/stage-operation")
async def pipeline_stage_operation(project_id: str, request: Request) -> Dict[str, Any]:
    """Non-blocking stage-level restart on Core (single authority).

    ops: regenerate (inject feedback + clear target~downstream + re-run)
         rollback   (clear target~downstream + re-run)
         resume     (re-run from target WITHOUT clearing artifacts)

    Returns immediately; the pipeline executes in a background task.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    op = str(body.get("op", "")).lower()
    stage_id = str(body.get("stage_id", "") or "")
    feedback = str(body.get("feedback", "") or "")
    config = body.get("config", {}) if isinstance(body.get("config"), dict) else {}

    if op not in ("regenerate", "rollback", "resume"):
        raise HTTPException(status_code=400, detail=f"Unknown op: {op}")

    store = get_pipeline_run_store()
    run = store.get_run_by_project(project_id)
    if not run:
        raise HTTPException(status_code=404, detail="No pipeline run for this project")
    run_id = run["run_id"]

    # Stop any existing running/paused engine to avoid double-run
    from core.api.core_facade import get_running_pipeline, unregister_pipeline
    existing = get_running_pipeline(project_id)
    if existing is not None:
        existing.force_terminate()
        unregister_pipeline(project_id)
        await asyncio.sleep(0.05)  # let old task's finally unregister before re-registering

    stages_raw = config.get("stages", [])
    engine = _reconstruct_engine(project_id, run_id, store, stages_raw or None)
    if engine is None:
        raise HTTPException(status_code=500, detail="Failed to reconstruct pipeline engine")

    state = dict(engine._state or {})
    state["session_id"] = run_id
    state["project_id"] = project_id
    # Carry over runtime config fields (needed by stage execution + artifact persistence)
    state["output_dir"] = config.get("output_dir", state.get("output_dir", ""))
    state["description"] = config.get("description", state.get("description", ""))
    state["app_name"] = config.get("app_name", state.get("app_name", ""))
    state["tokens_budget"] = config.get("tokens_budget", state.get("tokens_budget", 100000))
    state.setdefault("iteration", 1)
    state.setdefault("max_iterations", 3)
    state.setdefault("pass_rate", 0.0)
    state.setdefault("issues", {})
    state.setdefault("context", {})

    stages = engine._config.stages

    # Resolve target index by stage id / output_artifact / agent_id
    target_idx = 0
    for i, s in enumerate(stages):
        if stage_id and stage_id in (s.id, getattr(s, "output_artifact", ""), getattr(s, "agent_id", "")):
            target_idx = i
            break

    # Clear target + downstream artifacts for regenerate/rollback
    if op in ("regenerate", "rollback"):
        for i in range(target_idx, len(stages)):
            key = getattr(stages[i], "output_artifact", "")
            if key:
                state.pop(key, None)
            state.pop(f"_stage_{stages[i].id}_done", None)
        state.pop("_progress", None)
    if op == "regenerate" and feedback:
        state["_reject_feedback"] = feedback

    state["_current_stage_idx"] = target_idx
    state["phase"] = "executing"
    state["tokens_used"] = 0
    state.pop("error", None)
    state.pop("error_message", None)
    state.pop("_hitl_stage_id", None)
    state.pop("_hitl_output_artifact", None)
    state.pop("_hitl_phase_name", None)

    async def _run_stage_operation():
        try:
            await engine.run(project_id, state)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _log.error("Stage operation %s failed for %s: %s", op, project_id, str(e)[:500], exc_info=True)
            try:
                store.update_run_phase(run_id, "failed", str(e)[:500])
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    asyncio.create_task(_run_stage_operation())
    return {"status": "accepted", "run_id": run_id, "op": op, "target_idx": target_idx}


# ═══ v4.0: 跨会话 Pipeline 恢复 ═══

@router.post("/pipelines/runs/{run_id}/resume", response_model=Dict[str, Any])
async def resume_pipeline_run(run_id: str, body: dict = Body(default_factory=dict)):
    """Restart a failed/interrupted pipeline from its last completed stage.

    Uses the v4.0 resume_from_checkpoint with intelligent recovery:
    - Context length errors → auto-compress before retry
    - Other errors → retry from failed stage
    """
    from core.api.core_facade import get_pipeline_run_store

    store = get_pipeline_run_store()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    session_id = body.get("session_id", run.get("project_id", ""))
    config_data = run.get("config", {})

    engine = create_pipeline_engine(config=config_data)

    try:
        result = await engine.resume_from_checkpoint(run_id, session_id)
        return {"status": "resumed", "run_id": run_id, "result": dict(result)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:200])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])
