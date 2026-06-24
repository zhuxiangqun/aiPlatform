"""
App Studio API — conversational app creation, testing, and deployment.

自然语言对话驱动应用创建：
  1. 用户描述需求 → AI PM 对话澄清 → 生成 PRD
  2. 确认 PRD → 自动组装 Agent 团队 → 启动 Builder Pipeline
  3. Pipeline 执行中 → 前端实时展示阶段进度
  4. 完成后 → 运行测试 → 部署到 aiPlat-app
"""

from __future__ import annotations

import os
import shutil
import tempfile
import asyncio
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

router = APIRouter(prefix="/studio", tags=["studio"])


def _adapt_session_response(data: dict) -> dict:
    """将平台的 {reply, prd_ready, session_state} 格式适配为前端 {messages, prd, phase} 格式。"""
    adapted = dict(data)

    # reply → messages（前端期望 messages 数组）
    if "reply" in adapted and "messages" not in adapted:
        adapted["messages"] = [{"role": "pm", "content": adapted.pop("reply")}]

    # session_state → prd / project_id
    state = adapted.get("session_state") or {}
    if isinstance(state, dict):
        if "prd" in state and not adapted.get("prd"):
            adapted["prd"] = state["prd"]
        if "project_id" in state and not adapted.get("project_id"):
            adapted["project_id"] = state["project_id"]

    # prd_ready → phase
    if adapted.get("prd_ready"):
        adapted["phase"] = "prd_draft"

    # phase normalization for session responses
    if adapted.get("phase") in ("dialogue",):
        adapted["phase"] = "clarifying"

    return adapted


def _core(request: Request):
    client = getattr(request.app.state, "core_client", None)
    if not client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return client


# ━━━ Session (Chat) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/sessions")
async def create_session(request: Request, body: Dict[str, Any]):
    """创建新的 App Studio 会话。用户用自然语言描述需求。"""
    client = _core(request)
    requirement = str(body.get("requirement", "") or body.get("message", "") or "")
    if not requirement:
        raise HTTPException(status_code=400, detail="requirement is required")
    return _adapt_session_response(await client.create_builder_session(requirement))


@router.post("/sessions/{session_id}/chat")
async def chat_session(session_id: str, request: Request, body: Dict[str, Any]):
    """与 AI PM 对话，澄清需求。"""
    client = _core(request)
    message = str(body.get("message", "") or "")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    return _adapt_session_response(await client.builder_chat(session_id, message))


@router.post("/sessions/{session_id}/confirm")
async def confirm_session(session_id: str, request: Request):
    """确认 PRD，准备进入构建阶段。"""
    client = _core(request)
    return _adapt_session_response(await client.builder_confirm(session_id))


@router.post("/sessions/{session_id}/start")
async def start_pipeline(session_id: str, request: Request):
    """启动 Builder Pipeline。"""
    client = _core(request)
    return await client.builder_start(session_id)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """获取会话状态。"""
    client = _core(request)
    return _adapt_session_response(await client.get_builder_session(session_id))


# ━━━ Projects ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/projects")
async def list_projects(request: Request, limit: int = 100, offset: int = 0):
    """列出所有 App Studio 项目。"""
    client = _core(request)
    return await client.list_projects(limit=limit, offset=offset)


@router.post("/projects")
async def create_project(request: Request, body: Dict[str, Any]):
    """创建新项目（带团队选择和需求描述）。"""
    client = _core(request)
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return await client.create_project(body)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request):
    """获取项目详情。"""
    client = _core(request)
    return await client.get_project(project_id)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, request: Request):
    """删除项目。"""
    client = _core(request)
    return await client.delete_project(project_id)


@router.get("/projects/{project_id}/state")
async def get_project_state(project_id: str, request: Request):
    """获取项目 Pipeline 执行状态。"""
    client = _core(request)
    return await client.get_project_state(project_id)


@router.get("/projects/{project_id}/stream")
async def project_stream(project_id: str, request: Request):
    """SSE 实时推送 Pipeline 进度事件。"""
    from sse_starlette.sse import EventSourceResponse
    import json as _json

    client = _core(request)

    async def event_generator():
        try:
            async for event in client.stream_project_events(project_id):
                yield {"event": event.get("type", "message"), "data": _json.dumps(event)}
        except AttributeError:
            while True:
                import asyncio
                state = await client.get_project_state(project_id)
                yield {"event": "state", "data": _json.dumps(state)}
                await asyncio.sleep(3)

    return EventSourceResponse(event_generator())


@router.post("/projects/{project_id}/chat")
async def project_chat(project_id: str, request: Request, body: Dict[str, Any]):
    """在项目上下文中与 AI PM 对话。"""
    client = _core(request)
    message = str(body.get("message", "") or "")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    return await client.project_chat(project_id, message)


@router.post("/projects/{project_id}/confirm")
async def project_confirm(project_id: str, request: Request):
    """确认项目 PRD。"""
    client = _core(request)
    return await client.project_confirm(project_id)


@router.post("/projects/{project_id}/start")
async def project_start(project_id: str, request: Request):
    """启动项目 Pipeline。"""
    client = _core(request)
    return await client.project_start(project_id)


@router.post("/projects/{project_id}/approve")
async def project_approve(project_id: str, request: Request):
    """HITL：审批当前阶段。"""
    client = _core(request)
    return await client.project_approve(project_id)


@router.post("/projects/{project_id}/reject")
async def project_reject(project_id: str, request: Request, body: Dict[str, Any] = {}):
    """HITL：驳回当前阶段（带反馈）。"""
    client = _core(request)
    feedback = str(body.get("feedback", "") or "")
    return await client.project_reject(project_id, feedback)


@router.post("/projects/{project_id}/rollback/{stage_id}")
async def project_rollback(project_id: str, stage_id: str, request: Request):
    """回滚指定阶段。"""
    client = _core(request)
    return await client.project_rollback(project_id, stage_id)


@router.post("/projects/{project_id}/fix")
async def project_fix(project_id: str, request: Request):
    """启动自动修复 Pipeline。"""
    client = _core(request)
    return await client.project_fix(project_id)


# ━━━ Testing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/projects/{project_id}/test")
async def project_test(project_id: str, request: Request):
    """运行项目测试（调用 core 的 repo tests + E2E smoke）。"""
    client = _core(request)
    results: Dict[str, Any] = {"project_id": project_id}

    try:
        smoke = await client.run_e2e_smoke({"project_id": project_id})
        results["e2e_smoke"] = smoke
    except Exception as e:
        results["e2e_smoke"] = {"ok": False, "error": str(e)[:200]}

    try:
        repo = await client.run_repo_tests()
        results["repo_tests"] = repo
    except Exception as e:
        results["repo_tests"] = {"ok": False, "error": str(e)[:200]}

    results["all_passed"] = (
        bool((results.get("e2e_smoke") or {}).get("ok"))
        and bool((results.get("repo_tests") or {}).get("ok"))
    )
    return results


# ━━━ Agents & Teams ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/agents")
async def list_agents(request: Request):
    """列出可用 Agent 目录（供组装团队时选择）。"""
    client = _core(request)
    return await client.list_workspace_agents()


@router.get("/teams")
async def list_teams(request: Request):
    """列出已有团队。"""
    client = _core(request)
    return await client.list_teams()


@router.post("/teams")
async def create_team(request: Request, body: Dict[str, Any]):
    """创建新团队。"""
    client = _core(request)
    return await client.create_team(body)


@router.post("/teams/{team_id}/run")
async def run_team(team_id: str, request: Request, body: Dict[str, Any] = {}):
    """运行团队 Pipeline。"""
    client = _core(request)
    description = str(body.get("description", "") or "")
    return await client.run_team(team_id, description)


# ━━━ Deploy ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/projects/{project_id}/deploy")
async def download_deploy_package(project_id: str, request: Request):
    """下载部署包（zip 文件）。"""
    client = _core(request)
    url = await client.get_project_deploy_url(project_id)
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            resp = await http_client.get(url)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail="Deploy package not ready. Run pipeline first.")
        content_disposition = resp.headers.get("content-disposition", f'attachment; filename="{project_id}_deploy.zip"')
        return Response(
            content=resp.content,
            media_type="application/zip",
            headers={"Content-Disposition": content_disposition},
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Core unavailable: {str(e)}")


@router.post("/projects/{project_id}/deploy-to-app")
async def deploy_to_app(project_id: str, request: Request, body: Dict[str, Any] = {}):
    """部署项目到 aiPlat-app。
    1) 从 core 下载部署 zip
    2) 解压 → 注入到 app 的部署目录（符号链接版本管理）
    3) 异步健康检查 → 失败自动回滚
    4) 返回部署状态 + health_check_pending
    """
    client = _core(request)
    url = await client.get_project_deploy_url(project_id)

    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            resp = await http_client.get(url)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail="Deploy package not ready.")
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Core unavailable: {str(e)}")

    app_deploy_dir = os.getenv("AIPLAT_APP_DEPLOY_DIR", os.path.expanduser("~/.aiplat/apps"))
    project_base = Path(app_deploy_dir) / project_id
    version_dir = project_base / f"v_{int(time.time())}"
    current_link = project_base / "current"
    previous_link = project_base / "previous"

    os.makedirs(str(version_dir), exist_ok=True)

    tmp = tempfile.mktemp(suffix=".zip")
    try:
        with open(tmp, "wb") as f:
            f.write(resp.content)
        with zipfile.ZipFile(tmp, "r") as zf:
            for member in zf.namelist():
                zf.extract(member, str(version_dir))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    # Version management: current → previous, new → current
    if current_link.is_symlink() or current_link.exists():
        if previous_link.is_symlink():
            previous_link.unlink()
        if current_link.is_symlink():
            current_link.rename(previous_link)
        elif current_link.exists():
            shutil.move(str(current_link), str(previous_link))

    os.symlink(str(version_dir), str(current_link))

    app_url_root = os.getenv("AIPLAT_APP_BASE_URL", "http://localhost:8004")
    app_url = f"{app_url_root}/{project_id}"

    # Asynchronous health check
    deploy_events: list[dict] = []
    _deploy_events_by_project[project_id] = deploy_events
    deploy_events.append({"type": "deploy_start", "version": version_dir.name, "timestamp": time.time()})

    async def health_check_loop(max_wait=30):
        deploy_events.append({"type": "health_check_start", "max_wait": max_wait})
        for i in range(max_wait):
            try:
                async with httpx.AsyncClient(timeout=5.0) as hc:
                    check_resp = await hc.get(f"{app_url}/health")
                if check_resp.status_code == 200:
                    deploy_events.append({"type": "deploy_healthy", "elapsed_s": i + 1, "timestamp": time.time()})
                    return
            except Exception:
                if i < 3:
                    deploy_events.append({"type": "health_poll", "attempt": i + 1, "timestamp": time.time()})
            await asyncio.sleep(1)

        # Timeout → auto rollback
        deploy_events.append({"type": "health_timeout", "elapsed_s": max_wait, "timestamp": time.time()})
        try:
            _rollback(current_link, previous_link, project_base)
            deploy_events.append({"type": "rollback_success", "timestamp": time.time()})
        except Exception as e:
            deploy_events.append({"type": "rollback_failed_critical", "error": str(e), "timestamp": time.time()})

    asyncio.create_task(health_check_loop())

    # Register deployed app in platform's apps table (management UI visibility)
    platform_url = os.getenv("AIPLAT_PLATFORM_URL", "http://localhost:8003")
    asyncio.create_task(_register_studio_app(platform_url, project_id, app_url))

    return {
        "ok": True,
        "project_id": project_id,
        "deploy_dir": str(version_dir),
        "app_url": app_url,
        "health_check_pending": True,
    }


# In-memory deploy event store (connected to SSE stream endpoint)
_deploy_events_by_project: Dict[str, list] = {}


async def _register_studio_app(platform_url: str, project_id: str, app_url: str):
    """向平台注册 Studio 生成的应用，使其在管理界面可见。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(f"{platform_url}/platform/apps/register-from-studio", json={
                "app_id": f"studio_{project_id}",
                "name": project_id,
                "project_id": project_id,
                "app_url": app_url,
            })
    except Exception:
        pass  # 注册失败不阻塞部署流程


def _rollback(current_link: Path, previous_link: Path, project_base: Path):
    """Rollback to previous stable version symlink."""
    if previous_link.is_symlink() or previous_link.exists():
        if current_link.is_symlink():
            current_link.unlink()
        os.symlink(str(previous_link.resolve()), str(current_link))
        return
    # No previous version → remove current
    if current_link.is_symlink() or current_link.exists():
        current_link.unlink()
    # Remove version dirs
    for d in sorted(project_base.glob("v_*"), reverse=True)[1:]:
        shutil.rmtree(str(d), ignore_errors=True)


@router.get("/projects/{project_id}/deploy-stream")
async def project_deploy_stream(project_id: str, request: Request):
    """SSE 实时推送部署健康检查进度和日志。"""
    from sse_starlette.sse import EventSourceResponse
    import json as _json

    async def event_generator():
        last_idx = 0
        while True:
            events = _deploy_events_by_project.get(project_id, [])
            while last_idx < len(events):
                evt = events[last_idx]
                yield {"event": evt.get("type", "deploy"), "data": _json.dumps(evt)}
                last_idx += 1
            # Cleanup on terminal events
            if events and events[-1].get("type") in ("deploy_healthy", "rollback_success", "rollback_failed_critical"):
                _deploy_events_by_project.pop(project_id, None)
                return
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
