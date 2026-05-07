"""
Builder projects API router.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas_builder import (
    ProjectCreateRequest,
    BuilderChatRequest,
    BuilderRejectRequest,
    Project,
    ProjectListResponse,
)
from core.services.builder_project_service import BuilderProjectService

router = APIRouter(prefix="/builder")

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

_proj_svc: Optional[BuilderProjectService] = None


def _svc(rt: Optional[KernelRuntime] = None) -> BuilderProjectService:
    global _proj_svc
    if _proj_svc is None or (_proj_svc._model is None):
        model = None
        if rt and hasattr(rt, "adapter_manager") and rt.adapter_manager:
            try:
                model = rt.adapter_manager.get_default_adapter()
            except Exception:
                pass
        if model is None:
            try:
                import os
                from core.harness.utils.model_injection import create_selected_adapter
                provider = os.getenv("AIPLAT_LLM_PROVIDER") or os.getenv("DEEPSEEK_PROVIDER") or "deepseek"
                model_name = os.getenv("AIPLAT_LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
                model = create_selected_adapter(model_name=model_name)
            except Exception as e:
                print(f"[builder_projects] create_selected_adapter failed: {e}")
        _proj_svc = BuilderProjectService(model=model)
    return _proj_svc
    return _proj_svc


@router.post("/projects")
async def create_project(request: ProjectCreateRequest, rt: RuntimeDep = None):
    return await _svc(rt).create_project(request)


@router.get("/projects")
async def list_projects(rt: RuntimeDep = None):
    projects = await _svc(rt).list_projects()
    return ProjectListResponse(projects=projects, total=len(projects))


@router.get("/projects/{project_id}")
async def get_project(project_id: str, rt: RuntimeDep = None):
    p = await _svc(rt).get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, rt: RuntimeDep = None):
    ok = await _svc(rt).delete_project(project_id)
    return {"ok": ok}


@router.post("/projects/{project_id}/chat")
async def project_chat(project_id: str, request: BuilderChatRequest, rt: RuntimeDep = None):
    return await _svc(rt).chat(project_id, request.message)


@router.post("/projects/{project_id}/confirm")
async def project_confirm(project_id: str, request: dict = {}, rt: RuntimeDep = None):
    return await _svc(rt).confirm_prd(project_id, request.get("prd"))


@router.post("/projects/{project_id}/start")
async def project_start(project_id: str, rt: RuntimeDep = None):
    try:
        return await _svc(rt).start_pipeline(project_id)
    except Exception as e:
        import traceback
        print(f"[builder_projects] start_pipeline error: {e}")
        traceback.print_exc()
        raise HTTPException(500, str(e))


@router.post("/projects/{project_id}/approve")
async def project_approve(project_id: str, rt: RuntimeDep = None):
    return await _svc(rt).approve_stage(project_id)


@router.post("/projects/{project_id}/reject")
async def project_reject(project_id: str, request: BuilderRejectRequest, rt: RuntimeDep = None):
    return await _svc(rt).reject_stage(project_id, request.feedback)


@router.post("/projects/{project_id}/rollback/{stage_id:path}")
async def project_rollback(project_id: str, stage_id: str, rt: RuntimeDep = None):
    if stage_id == "prd":
        return await _svc(rt).rollback_prd(project_id)
    return await _svc(rt).rollback_stage(project_id, stage_id)


@router.post("/projects/{project_id}/fix")
async def project_start_fix(project_id: str, rt: RuntimeDep = None):
    return await _svc(rt).start_fix(project_id)


@router.get("/projects/{project_id}/state")
async def project_state(project_id: str, rt: RuntimeDep = None):
    return await _svc(rt).get_project_state(project_id)


@router.get("/projects/{project_id}/deploy")
async def project_downloads_deploy(project_id: str, rt: RuntimeDep = None):
    import shutil, tempfile, os, zipfile
    deploy_dir = await _svc(rt).get_deploy_dir(project_id)
    if not deploy_dir or not os.path.exists(deploy_dir):
        raise HTTPException(404, "No deploy package available. Wait for pipeline to complete.")
    tmp = tempfile.mktemp(suffix=".zip")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(deploy_dir):
                for file in files:
                    fp = os.path.join(root, file)
                    arcname = os.path.relpath(fp, deploy_dir)
                    zf.write(fp, arcname)
        from fastapi.responses import FileResponse
        return FileResponse(tmp, media_type="application/zip", filename=f"{project_id}_deploy.zip")
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Agent Insights ──────────────────────────────────────────────

@router.get("/agent-insight/{agent_id}")
async def agent_insight(agent_id: str):
    from core.services.agent_insight_service import AgentInsightService
    svc = AgentInsightService()
    insight = await svc.get_agent_insight(agent_id)
    if not insight:
        return {"agent_id": agent_id, "total_runs": 0, "rejection_rate": 0, "qa_rollback_rate": 0, "first_pass_rate": 0, "output_completeness": 0, "recent_runs": []}
    return {"agent_id": agent_id, **insight}


@router.get("/agent-insights")
async def all_agent_insights():
    from core.services.agent_insight_service import AgentInsightService
    svc = AgentInsightService()
    return await svc.get_all_insights()


@router.post("/agent-insights/refresh")
async def refresh_agent_insights():
    import json, os
    from core.services.agent_insight_service import AgentInsightService
    projects_file = os.path.join(os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")), "projects.json")
    projects_data = []
    if os.path.exists(projects_file):
        try:
            with open(projects_file, "r") as f:
                projects_data = json.load(f).get("projects", [])
        except Exception:
            pass
    svc = AgentInsightService()
    result = svc.refresh_from_projects(projects_data)
    return {"agents": len(result), "ok": True}


# ── Prompt Version Management ──────────────────────────────────

@router.get("/prompt-versions/{agent_id}")
async def list_prompt_versions(agent_id: str):
    from core.services.prompt_version_service import PromptVersionService
    svc = PromptVersionService()
    return {"agent_id": agent_id, "versions": svc.list_versions(agent_id)}


@router.post("/prompt-versions/{agent_id}")
async def save_prompt_version(agent_id: str, request: dict):
    from core.services.prompt_version_service import PromptVersionService
    svc = PromptVersionService()
    entry = svc.save_version(agent_id, request.get("prompt", ""), request.get("description", ""))
    return entry


@router.post("/prompt-versions/{agent_id}/rollback/{version}")
async def rollback_prompt(agent_id: str, version: int):
    from core.services.prompt_version_service import PromptVersionService
    svc = PromptVersionService()
    prompt = svc.rollback(agent_id, version)
    if not prompt:
        raise HTTPException(404, "Version not found")
    return {"agent_id": agent_id, "version": version, "ok": True}
