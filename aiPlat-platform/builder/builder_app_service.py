"""
App service — publish workflows as apps (API / Chat / Webhook).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Any, Dict, List, Optional

from core.utils.ids import new_prefixed_id
from storage.sqlite import (
    list_apps, get_app, create_app, create_studio_app, delete_app,
    create_webhook_secret, get_webhook_secret,
    get_workflow, list_workflow_runs,
)
from storage import sqlite as platform_store

_logger = logging.getLogger("aiplat.platform.app_service")


class AppService:

    async def publish(self, workflow_id: str, name: str, mode: str = "chat", description: str = "") -> Dict[str, Any]:
        wf = get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"workflow not found: {workflow_id}")
        if not name.strip():
            name = wf.get("name", "未命名") + (" Chat" if mode == "chat" else " API" if mode == "api" else " Webhook")
        app_id = new_prefixed_id("app")
        app = create_app(app_id, name.strip(), workflow_id, mode, description.strip())
        if mode == "webhook":
            secret = secrets.token_hex(24)
            create_webhook_secret(app_id, secret)
            app["webhook_secret"] = secret
        return app

    def register_studio(self, app_id: str, name: str, project_id: str, app_url: str = "") -> Dict[str, Any]:
        """注册 Studio 生成的应用。不要求 workflow_id，写入 capability_type='studio'。"""
        import time
        return create_studio_app(app_id, name or project_id, project_id, app_url)

    async def list(self) -> List[Dict[str, Any]]:
        apps = list_apps()
        for a in apps:
            try:
                wf = get_workflow(a["workflow_id"])
                a["workflow_name"] = wf.get("name", "") if wf else ""
            except Exception:
                a["workflow_name"] = ""
            # Extract app_url from description for Studio apps
            if a.get("capability_type") == "studio" and "Studio 生成 · " in (a.get("description") or ""):
                a["app_url"] = (a["description"] or "").replace("Studio 生成 · ", "")
        return apps

    async def get(self, app_id: str) -> Optional[Dict[str, Any]]:
        app = get_app(app_id)
        if not app:
            return None
        try:
            wf = get_workflow(app["workflow_id"])
            app["workflow_name"] = wf.get("name", "") if wf else ""
            app["nodes"] = (wf.get("nodes") or []) if wf else []
            app["edges"] = (wf.get("edges") or []) if wf else []
        except Exception:
            app["workflow_name"] = ""
            app["nodes"] = []
            app["edges"] = []
        if app["mode"] == "webhook":
            app["webhook_secret"] = get_webhook_secret(app_id) or ""
        return app

    async def delete(self, app_id: str) -> bool:
        # ── Cascade cleanup for factory-deployed apps ──
        if app_id.startswith("factory_"):
            import json, os, shutil
            project_id = app_id.replace("factory_", "", 1)
            # Clear deploy_dir from projects.json
            projects_file = os.path.join(
                os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
                "projects.json",
            )
            if os.path.exists(projects_file):
                try:
                    with open(projects_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for p in data.get("projects", []):
                        if p.get("project_id") == project_id:
                            p["deploy_dir"] = ""
                            p["updated_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
                            break
                    tmp = projects_file + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, projects_file)
                except Exception:
                    pass  # noqa: cleanup-best-effort
            # Remove deployed files from disk
            deploy_root = os.path.join(
                os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
                "apps", project_id,
            )
            if os.path.isdir(deploy_root):
                try:
                    shutil.rmtree(deploy_root)
                except OSError:
                    pass  # noqa: cleanup-best-effort
        return delete_app(app_id)


    def _build_stages_from_nodes(self, nodes: list, edges: list) -> list:
        # P1-9 收敛（§10 防并行实现）：委托 workflow_service._nodes_to_stages 唯一实现。
        # 原精简版缺 output_artifact/hitl/model/agent_type 等字段（PipelineStageConfig
        # extra=ignore 兜底，只增不减）。
        from builder.builder_workflow_service import WorkflowService
        return WorkflowService()._nodes_to_stages(nodes, edges)

    async def run_api(self, app_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """API mode: sync execute and return output."""
        app = get_app(app_id)
        if not app:
            raise ValueError(f"app not found: {app_id}")
        wf = get_workflow(app["workflow_id"])
        if not wf:
            raise ValueError(f"workflow not found: {app['workflow_id']}")
        nodes = wf.get("nodes") or []
        edges = wf.get("edges") or []
        user_input = str(inputs.get("input", inputs.get("message", "")))
        stages = self._build_stages_from_nodes(nodes, edges)
        from builder.builder_project_service import BuilderProjectService
        from builder.builder_team_service import BuilderTeamService
        from core.schemas_builder import ProjectCreateRequest
        svc = BuilderProjectService(team_service=BuilderTeamService())
        proj = await svc.create_project(ProjectCreateRequest(
            name=f"{app['name']}-api-run",
            description=f"API run for app {app_id}",
            stages=stages,
        ))
        from storage.sqlite import record_workflow_run
        record_workflow_run(app["workflow_id"], proj.project_id, f"api:{user_input[:30]}")
        import asyncio as _asyncio, concurrent.futures as _cf
        _cf.ThreadPoolExecutor(max_workers=1).submit(
            _asyncio.run, svc.start_pipeline(proj.project_id)).result(timeout=300)
        return {"run_id": proj.project_id, "app_id": app_id, "mode": "api"}

    async def run_chat(self, app_id: str, message: str) -> Dict[str, Any]:
        """Chat mode: execute workflow with conversation context."""
        app = get_app(app_id)
        if not app:
            raise ValueError(f"app not found: {app_id}")
        wf = get_workflow(app["workflow_id"])
        if not wf:
            raise ValueError(f"workflow not found: {app['workflow_id']}")
        if not message.strip():
            raise ValueError("message is required")
        nodes = wf.get("nodes") or []
        edges = wf.get("edges") or []
        stages = self._build_stages_from_nodes(nodes, edges)
        from builder.builder_project_service import BuilderProjectService
        from builder.builder_team_service import BuilderTeamService
        from core.schemas_builder import ProjectCreateRequest
        svc = BuilderProjectService(team_service=BuilderTeamService())
        proj = await svc.create_project(ProjectCreateRequest(
            name=f"{app['name']}-chat",
            description=f"Chat message: {message[:50]}",
            stages=stages,
        ))
        from storage.sqlite import record_workflow_run
        record_workflow_run(app["workflow_id"], proj.project_id, f"chat:{message[:30]}")
        import asyncio as _asyncio, concurrent.futures as _cf
        _cf.ThreadPoolExecutor(max_workers=1).submit(
            _asyncio.run, svc.start_pipeline(proj.project_id)).result(timeout=300)
        return {"run_id": proj.project_id, "app_id": app_id, "input": message, "mode": "chat"}

    async def run_webhook(self, app_id: str, secret: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Webhook mode: verify secret, execute async."""
        stored = get_webhook_secret(app_id)
        if not stored or not hmac.compare_digest(stored, secret):
            raise ValueError("invalid webhook secret")
        app = get_app(app_id)
        if not app:
            raise ValueError(f"app not found: {app_id}")
        wf = get_workflow(app["workflow_id"])
        if not wf:
            raise ValueError(f"workflow not found: {app['workflow_id']}")
        nodes = wf.get("nodes") or []
        edges = wf.get("edges") or []
        user_input = str(body.get("input", body.get("message", "")))
        stages = self._build_stages_from_nodes(nodes, edges)
        from builder.builder_project_service import BuilderProjectService
        from builder.builder_team_service import BuilderTeamService
        from core.schemas_builder import ProjectCreateRequest
        svc = BuilderProjectService(team_service=BuilderTeamService())
        proj = await svc.create_project(ProjectCreateRequest(
            name=f"{app['name']}-webhook",
            description=f"Webhook trigger",
            stages=stages,
        ))
        from storage.sqlite import record_workflow_run
        record_workflow_run(app["workflow_id"], proj.project_id, f"webhook:{user_input[:30]}")
        import asyncio as _asyncio, concurrent.futures as _cf
        _cf.ThreadPoolExecutor(max_workers=1).submit(
            _asyncio.run, svc.start_pipeline(proj.project_id)).result(timeout=300)
        return {"run_id": proj.project_id, "app_id": app_id, "mode": "webhook"}
