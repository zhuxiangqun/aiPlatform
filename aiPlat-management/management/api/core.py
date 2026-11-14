"""
Core Layer Management API Router

This router provides unified API endpoints for core layer management.
It calls aiPlat-core layer's REST API (running on port 8002) for actual operations.

Architecture:
- aiPlat-management (this layer): Management system, unified API entry point
- aiPlat-core (8002): Core business layer, actual implementation
"""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional, List, Dict, Any
import httpx
import time
import secrets

from ..core_client import CoreAPIClient, CoreAPIClientConfig


router = APIRouter(prefix="/core", tags=["core"])

# Core API client configuration
_core_client: Optional[CoreAPIClient] = None


def get_core_client() -> CoreAPIClient:
    """Get or create the core API client."""
    global _core_client
    if _core_client is None:
        config = CoreAPIClientConfig(
            timeout=30.0
        )
        _core_client = CoreAPIClient(config)
    return _core_client


# ==================== System Overview ====================


@router.get("/overview")
async def get_overview(request: Request):
    """Get aggregated system overview (4-layer health + stats).

    Args:
        request: FastAPI Request。
    """
    try:
        client = get_core_client()
        refresh = request.query_params.get("refresh", "false") == "true"
        return await client.get_overview(refresh=refresh)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Runs (Platform Execution Contract) ====================


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """获取 run。

    Args:
        run_id: 运行 ID。
    """
    try:
        client = get_core_client()
        return await client.get_run(run_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/runs/{run_id}/cost")
async def get_run_cost(run_id: str, tenant_id: Optional[str] = None):
    """获取 run_cost。

    Args:
        run_id: 运行 ID。
        tenant_id: 租户 ID。
    """
    try:
        client = get_core_client()
        return await client.get_run_cost(run_id, tenant_id=tenant_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Approvals ====================


@router.get("/approvals/pending")
async def list_pending_approvals(
    user_id: Optional[str] = None,
    order_by: str = "priority_score",
    order_dir: str = "desc",
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    """列出 pending_approvals。

    Args:
        user_id: 用户 ID。
        order_by: order_by 参数。
        order_dir: order_dir 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        return await client.list_pending_approvals(user_id=user_id, order_by=order_by, order_dir=order_dir, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/approvals/{request_id}")
async def get_approval_request(request_id: str):
    """获取 approval_request。

    Args:
        request_id: request 标识。
    """
    try:
        client = get_core_client()
        return await client.get_approval_request(request_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/approvals/{request_id}/approve")
async def approve_approval_request(request_id: str, body: dict):
    """approve_approval_request。

    Args:
        request_id: request 标识。
        body: 请求体。
    """
    try:
        client = get_core_client()
        return await client.approve_request(
            request_id,
            approved_by=str((body or {}).get("approved_by") or "admin"),
            comments=str((body or {}).get("comments") or ""),
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/approvals/{request_id}/reject")
async def reject_approval_request(request_id: str, body: dict):
    """reject_approval_request。

    Args:
        request_id: request 标识。
        body: 请求体。
    """
    try:
        client = get_core_client()
        return await client.reject_request(
            request_id,
            rejected_by=str((body or {}).get("rejected_by") or "admin"),
            comments=str((body or {}).get("comments") or ""),
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Skill Management ====================

@router.get("/skills")
async def list_skills(
    category: Optional[str] = None,
    status: Optional[str] = None,
    enabled_only: bool = False,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all skills.

    Args:
        category: category 参数。
        status: status 参数。
        enabled_only: enabled_only 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.list_skills(category=category, status=status, enabled_only=enabled_only, limit=limit, offset=offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills")
async def create_skill(skill: dict):
    """Create a new skill.

    Args:
        skill: skill 参数。
    """
    try:
        client = get_core_client()
        result = await client.create_skill(skill)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Get skill details.

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        result = await client.get_skill(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, updates: dict):
    """Update skill.

    Args:
        skill_id: Skill ID。
        updates: updates 参数。
    """
    try:
        client = get_core_client()
        result = await client.update_skill(skill_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, delete_files: bool = False):
    """Delete skill (default soft delete; delete_files=true for hard delete).

    Args:
        skill_id: Skill ID。
        delete_files: delete_files 参数。
    """
    try:
        client = get_core_client()
        result = await client.delete_skill(skill_id, delete_files=delete_files)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/enable")
async def enable_skill(skill_id: str):
    """Enable skill.

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        result = await client.enable_skill(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/disable")
async def disable_skill(skill_id: str):
    """Disable skill.

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        result = await client.disable_skill(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/restore")
async def restore_skill(skill_id: str):
    """Restore a deprecated skill.

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.restore_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== MCP Management ====================


@router.get("/mcp/servers")
async def list_mcp_servers():
    """List MCP servers (filesystem-backed)."""
    try:
        client = get_core_client()
        return await client.list_mcp_servers()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/mcp/servers/{server_name}/enable")
async def enable_mcp_server(server_name: str):
    """Enable MCP server.

    Args:
        server_name: server_name 参数。
    """
    try:
        client = get_core_client()
        return await client.enable_mcp_server(server_name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/mcp/servers/{server_name}/disable")
async def disable_mcp_server(server_name: str):
    """Disable MCP server.

    Args:
        server_name: server_name 参数。
    """
    try:
        client = get_core_client()
        return await client.disable_mcp_server(server_name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Workspace (user-facing) ====================


@router.get("/workspace/skills")
async def list_workspace_skills(
    category: Optional[str] = None,
    status: Optional[str] = None,
    enabled_only: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    """列出 workspace_skills。

    Args:
        category: category 参数。
        status: status 参数。
        enabled_only: enabled_only 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        return await client.list_workspace_skills(category, status, enabled_only=enabled_only, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills")
async def create_workspace_skill(payload: dict):
    """创建 workspace_skill。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.create_workspace_skill(payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}")
async def get_workspace_skill(skill_id: str):
    """获取 workspace_skill。

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/workspace/skills/{skill_id}")
async def update_workspace_skill(skill_id: str, payload: dict):
    """更新 workspace_skill。

    Args:
        skill_id: Skill ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.update_workspace_skill(skill_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/execute")
async def execute_workspace_skill(skill_id: str, payload: dict):
    """execute_workspace_skill。

    Args:
        skill_id: Skill ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.execute_workspace_skill(skill_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/enable")
async def enable_workspace_skill(skill_id: str):
    """enable_workspace_skill。

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.enable_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/disable")
async def disable_workspace_skill(skill_id: str):
    """disable_workspace_skill。

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.disable_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/restore")
async def restore_workspace_skill(skill_id: str):
    """restore_workspace_skill。

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.restore_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/skills/{skill_id}")
async def delete_workspace_skill(skill_id: str, delete_files: bool = False):
    """删除 workspace_skill。

    Args:
        skill_id: Skill ID。
        delete_files: delete_files 参数。
    """
    try:
        client = get_core_client()
        return await client.delete_workspace_skill(skill_id, delete_files=delete_files)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Workspace Skill Installer (open-source skills) ====================


@router.post("/workspace/skills/installer/plan")
async def plan_workspace_skill_install(payload: dict):
    """plan_workspace_skill_install。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.plan_workspace_skill_install(payload or {})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/installer/install")
async def install_workspace_skill(payload: dict):
    """install_workspace_skill。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.install_workspace_skill(payload or {})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/installer/update/{skill_id}")
async def update_workspace_skill_install(skill_id: str, payload: dict):
    """更新 workspace_skill_install。

    Args:
        skill_id: Skill ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.update_workspace_skill_install(skill_id, payload or {})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/installer/uninstall/{skill_id}")
async def uninstall_workspace_skill_install(skill_id: str, delete_files: bool = True):
    """uninstall_workspace_skill_install。

    Args:
        skill_id: Skill ID。
        delete_files: delete_files 参数。
    """
    try:
        client = get_core_client()
        return await client.uninstall_workspace_skill_install(skill_id, delete_files=delete_files)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/installer/resolve-head")
async def resolve_workspace_skill_install_head(payload: dict):
    """resolve_workspace_skill_install_head。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        url = str((payload or {}).get("url") or "")
        return await client.resolve_workspace_skill_install_head(url)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/sign-all")
async def sign_all_workspace_skills(payload: dict):
    """sign_all_workspace_skills。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client._request("POST", "/api/core/workspace/skills/sign-all", json=payload or {})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ── Engine scope agents (核心能力层) ──

@router.get("/agents")
async def list_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """列出 agents。

    Args:
        agent_type: agent_type 参数。
        status: status 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        return await client.list_agents(agent_type, status, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents")
async def create_agent(payload: dict):
    """创建 agent。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.create_agent(payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """获取 agent。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, payload: dict):
    """更新 agent。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.update_agent(agent_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除 agent。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.delete_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents/{agent_id}/start")
async def start_agent(agent_id: str):
    """start_agent。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.start_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """stop_agent。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.stop_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/agents/{agent_id}/skills")
async def get_agent_skills(agent_id: str):
    """获取 agent_skills。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_agent_skills(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/agents/{agent_id}/tools")
async def get_agent_tools(agent_id: str):
    """获取 agent_tools。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_agent_tools(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/agents/{agent_id}/sop")
async def get_agent_sop(agent_id: str):
    """获取 agent_sop。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_agent_sop(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/models")
async def list_models(
    provider: Optional[str] = None,
    status: Optional[str] = None,
):
    """List all available LLM models.

    Args:
        provider: provider 参数。
        status: status 参数。
    """
    try:
        client = get_core_client()
        return await client.list_models(provider=provider, status=status)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/agents/{agent_id}/versions")
async def get_agent_versions(agent_id: str):
    """获取 agent_versions。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_agent_versions(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents/{agent_id}/versions/{version}/rollback")
async def rollback_agent_version(agent_id: str, version: str):
    """rollback_agent_version。

    Args:
        agent_id: Agent ID。
        version: version 参数。
    """
    try:
        client = get_core_client()
        return await client.rollback_agent_version(agent_id, version)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ── Workspace scope agents (应用层) ──

@router.get("/workspace/agents")
async def list_workspace_agents(
    type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """列出 workspace_agents。

    Args:
        type: type 参数。
        status: status 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        return await client.list_workspace_agents(type, status, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents")
async def create_workspace_agent(payload: dict):
    """创建 workspace_agent。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.create_workspace_agent(payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/auto-fill")
async def auto_fill_workspace_agent(payload: dict):
    """auto_fill_workspace_agent。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.auto_fill_workspace_agent(payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/seeds")
async def list_workspace_agent_seeds():
    """列出 workspace_agent_seeds。
    """
    try:
        client = get_core_client()
        return await client.list_workspace_agent_seeds()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}")
async def get_workspace_agent(agent_id: str):
    """获取 workspace_agent。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/workspace/agents/{agent_id}")
async def update_workspace_agent(agent_id: str, payload: dict):
    """更新 workspace_agent。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.update_workspace_agent(agent_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}")
async def delete_workspace_agent(agent_id: str):
    """删除 workspace_agent。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.delete_workspace_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/execute")
async def execute_workspace_agent(agent_id: str, payload: dict):
    """execute_workspace_agent。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.execute_workspace_agent(agent_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/skills")
async def get_workspace_agent_skills(agent_id: str):
    """获取 workspace_agent_skills。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_skills(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/skills")
async def bind_workspace_agent_skills(agent_id: str, payload: dict):
    """bind_workspace_agent_skills。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        skill_ids = list(payload.get("skill_ids") or [])
        return await client.bind_workspace_agent_skills(agent_id, skill_ids)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}/skills/{skill_id}")
async def unbind_workspace_agent_skill(agent_id: str, skill_id: str):
    """unbind_workspace_agent_skill。

    Args:
        agent_id: Agent ID。
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.unbind_workspace_agent_skill(agent_id, skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/tools")
async def get_workspace_agent_tools(agent_id: str):
    """获取 workspace_agent_tools。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_tools(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/tools")
async def bind_workspace_agent_tools(agent_id: str, payload: dict):
    """bind_workspace_agent_tools。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        tool_ids = list(payload.get("tool_ids") or [])
        return await client.bind_workspace_agent_tools(agent_id, tool_ids)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}/tools/{tool_id}")
async def unbind_workspace_agent_tool(agent_id: str, tool_id: str):
    """unbind_workspace_agent_tool。

    Args:
        agent_id: Agent ID。
        tool_id: tool 标识。
    """
    try:
        client = get_core_client()
        return await client.unbind_workspace_agent_tool(agent_id, tool_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/sop")
async def get_workspace_agent_sop(agent_id: str):
    """获取 workspace_agent_sop。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_sop(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/mcp")
async def get_workspace_agent_mcp(agent_id: str):
    """获取 workspace_agent_mcp。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_mcp(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/mcp")
async def bind_workspace_agent_mcp(agent_id: str, payload: dict):
    """bind_workspace_agent_mcp。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        mcp_ids = list(payload.get("mcp_ids") or [])
        return await client.bind_workspace_agent_mcp(agent_id, mcp_ids)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}/mcp/{mcp_id}")
async def unbind_workspace_agent_mcp(agent_id: str, mcp_id: str):
    """unbind_workspace_agent_mcp。

    Args:
        agent_id: Agent ID。
        mcp_id: mcp 标识。
    """
    try:
        client = get_core_client()
        return await client.unbind_workspace_agent_mcp(agent_id, mcp_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/execution-help")
async def get_workspace_agent_execution_help(agent_id: str):
    """获取 workspace_agent_execution_help。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_execution_help(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/workflows")
async def get_workspace_agent_workflows(agent_id: str):
    """获取 workspace_agent_workflows。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_workflows(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/workflows")
async def bind_workspace_agent_workflows(agent_id: str, payload: dict):
    """bind_workspace_agent_workflows。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        workflow_ids = list(payload.get("workflow_ids") or [])
        return await client.bind_workspace_agent_workflows(agent_id, workflow_ids)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}/workflows/{workflow_id}")
async def unbind_workspace_agent_workflow(agent_id: str, workflow_id: str):
    """unbind_workspace_agent_workflow。

    Args:
        agent_id: Agent ID。
        workflow_id: workflow 标识。
    """
    try:
        client = get_core_client()
        return await client.unbind_workspace_agent_workflow(agent_id, workflow_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/agents")
async def get_workspace_agent_sub_agents(agent_id: str):
    """获取 workspace_agent_sub_agents。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_sub_agents(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/agents")
async def bind_workspace_agent_sub_agents(agent_id: str, payload: dict):
    """bind_workspace_agent_sub_agents。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        agent_ids = list(payload.get("agent_ids") or [])
        return await client.bind_workspace_agent_sub_agents(agent_id, agent_ids)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}/agents/{sub_agent_id}")
async def unbind_workspace_agent_sub_agent(agent_id: str, sub_agent_id: str):
    """unbind_workspace_agent_sub_agent。

    Args:
        agent_id: Agent ID。
        sub_agent_id: sub_agent 标识。
    """
    try:
        client = get_core_client()
        return await client.unbind_workspace_agent_sub_agent(agent_id, sub_agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/history")
async def get_workspace_agent_history(agent_id: str, limit: int = 100, offset: int = 0):
    """获取 workspace_agent_history。

    Args:
        agent_id: Agent ID。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_history(agent_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/versions")
async def get_workspace_agent_versions(agent_id: str):
    """获取 workspace_agent_versions。

    Args:
        agent_id: Agent ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_agent_versions(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/versions")
async def create_workspace_agent_version(agent_id: str, payload: dict):
    """创建 workspace_agent_version。

    Args:
        agent_id: Agent ID。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client.create_workspace_agent_version(agent_id, str((payload or {}).get("changes", "")))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/versions/{version}/rollback")
async def rollback_workspace_agent_version(agent_id: str, version: str):
    """rollback_workspace_agent_version。

    Args:
        agent_id: Agent ID。
        version: version 参数。
    """
    try:
        client = get_core_client()
        return await client.rollback_workspace_agent_version(agent_id, version)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ── Workspace tools (应用库 Tool) ──

@router.get("/workspace/tools")
async def list_workspace_tools():
    """列出 workspace_tools。
    """
    try:
        client = get_core_client()
        return await client._request("GET", "/api/core/workspace/tools")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/tools")
async def create_workspace_tool(payload: dict):
    """创建 workspace_tool。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client._request("POST", "/api/core/workspace/tools", json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/tools/{tool_name}")
async def delete_workspace_tool(tool_name: str):
    """删除 workspace_tool。

    Args:
        tool_name: tool_name 参数。
    """
    try:
        client = get_core_client()
        return await client._request("DELETE", f"/api/core/workspace/tools/{tool_name}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/workspace/tools/{tool_name}")
async def update_workspace_tool(tool_name: str, payload: dict):
    """更新 workspace_tool。

    Args:
        tool_name: tool_name 参数。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client._request("PUT", f"/api/core/workspace/tools/{tool_name}", json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/tools/{tool_name}/sign")
async def sign_workspace_tool(tool_name: str, payload: dict):
    """sign_workspace_tool。

    Args:
        tool_name: tool_name 参数。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client._request("POST", f"/api/core/workspace/tools/{tool_name}/sign", json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/tools/{tool_name}/source")
async def get_workspace_tool_source(tool_name: str):
    """获取 workspace_tool_source。

    Args:
        tool_name: tool_name 参数。
    """
    try:
        client = get_core_client()
        return await client._request("GET", f"/api/core/workspace/tools/{tool_name}/source")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/workspace/tools/{tool_name}/source")
async def update_workspace_tool_source(tool_name: str, payload: dict):
    """更新 workspace_tool_source。

    Args:
        tool_name: tool_name 参数。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client._request("PUT", f"/api/core/workspace/tools/{tool_name}/source", json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/tools/{tool_name}/reload")
async def reload_workspace_tool(tool_name: str):
    """reload_workspace_tool。

    Args:
        tool_name: tool_name 参数。
    """
    try:
        client = get_core_client()
        return await client._request("POST", f"/api/core/workspace/tools/{tool_name}/reload")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/tools/discover")
async def discover_workspace_tools():
    """discover_workspace_tools。
    """
    try:
        client = get_core_client()
        return await client._request("POST", "/api/core/workspace/tools/discover")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}/executions")
async def list_workspace_skill_executions(skill_id: str, limit: int = 100, offset: int = 0):
    """列出 workspace_skill_executions。

    Args:
        skill_id: Skill ID。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        return await client.list_workspace_skill_executions(skill_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}/versions")
async def get_workspace_skill_versions(skill_id: str):
    """获取 workspace_skill_versions。

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_skill_versions(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}/active-version")
async def get_workspace_skill_active_version(skill_id: str):
    """获取 workspace_skill_active_version。

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        return await client.get_workspace_skill_active_version(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/versions/{version}/rollback")
async def rollback_workspace_skill_version(skill_id: str, version: str):
    """rollback_workspace_skill_version。

    Args:
        skill_id: Skill ID。
        version: version 参数。
    """
    try:
        client = get_core_client()
        return await client.rollback_workspace_skill_version(skill_id, version)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/mcp/servers")
async def list_workspace_mcp_servers():
    """列出 workspace_mcp_servers。
    """
    try:
        client = get_core_client()
        return await client.list_workspace_mcp_servers()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/mcp/servers/{server_name}/enable")
async def enable_workspace_mcp_server(server_name: str):
    """enable_workspace_mcp_server。

    Args:
        server_name: server_name 参数。
    """
    try:
        client = get_core_client()
        return await client.enable_workspace_mcp_server(server_name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/mcp/servers/{server_name}/disable")
async def disable_workspace_mcp_server(server_name: str):
    """disable_workspace_mcp_server。

    Args:
        server_name: server_name 参数。
    """
    try:
        client = get_core_client()
        return await client.disable_workspace_mcp_server(server_name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/mcp/servers/{server_name}/tools")
async def list_mcp_server_tools(server_name: str, timeout_seconds: int = 25):
    """列出 mcp_server_tools。

    Args:
        server_name: server_name 参数。
        timeout_seconds: timeout_seconds 参数。
    """
    try:
        client = get_core_client()
        qs = f"?timeout_seconds={int(timeout_seconds)}" if timeout_seconds else ""
        return await client._request("GET", f"/api/core/workspace/mcp/servers/{server_name}/tools{qs}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/mcp/servers/{server_name}/test-invoke")
async def test_invoke_workspace_mcp_server(server_name: str, payload: dict):
    """test_invoke_workspace_mcp_server。

    Args:
        server_name: server_name 参数。
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client._request("POST", f"/api/core/workspace/mcp/servers/{server_name}/test-invoke", json=payload or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/mcp/servers/{server_name}")
async def get_workspace_mcp_server(server_name: str):
    """获取 workspace_mcp_server。

    Args:
        server_name: server_name 参数。
    """
    try:
        client = get_core_client()
        return await client._request("GET", f"/api/core/workspace/mcp/servers/{server_name}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/mcp/servers")
async def upsert_workspace_mcp_server(payload: dict):
    """upsert_workspace_mcp_server。

    Args:
        payload: 载荷 dict。
    """
    try:
        client = get_core_client()
        return await client._request("POST", "/api/core/workspace/mcp/servers", json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/mcp/servers/{server_name}")
async def delete_workspace_mcp_server(server_name: str):
    """删除 workspace_mcp_server。

    Args:
        server_name: server_name 参数。
    """
    try:
        client = get_core_client()
        return await client._request("DELETE", f"/api/core/workspace/mcp/servers/{server_name}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ── Observation SSE stream ──

@router.get("/core/observation/runs/{run_id}/stream")
async def observation_stream(run_id: str):
    """Proxy SSE observation stream to core (stream pass-through).

    Args:
        run_id: 运行 ID。
    """
    import httpx, os
    core_url = f"{os.getenv('AIPLAT_CORE_URL', 'http://localhost:8002')}/api/core/observation/runs/{run_id}/stream"
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.send(client.build_request("GET", core_url), stream=True)
        resp.raise_for_status()
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            resp.aiter_bytes(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )


@router.get("/skills/{skill_id}/agents")
async def get_skill_agents(skill_id: str):
    """Get agents bound to this skill.

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        result = await client.get_skill_agents(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}/binding-stats")
async def get_skill_binding_stats(skill_id: str):
    """Get skill binding statistics.

    Args:
        skill_id: Skill ID。
    """
    try:
        client = get_core_client()
        result = await client.get_skill_binding_stats(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Skill version management
@router.get("/skills/{skill_id}/versions")
async def get_skill_versions(
    skill_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get skill version list.

    Args:
        skill_id: Skill ID。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.get_skill_versions(skill_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}/versions/{version}")
async def get_skill_version(skill_id: str, version: str):
    """Get specific skill version.

    Args:
        skill_id: Skill ID。
        version: version 参数。
    """
    try:
        client = get_core_client()
        result = await client.get_skill_version(skill_id, version)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/versions/{version}/rollback")
async def rollback_skill_version(skill_id: str, version: str):
    """Rollback skill to specific version.

    Args:
        skill_id: Skill ID。
        version: version 参数。
    """
    try:
        client = get_core_client()
        result = await client.rollback_skill_version(skill_id, version)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Skill execution
@router.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, data: dict):
    """Execute skill with input.

    Args:
        skill_id: Skill ID。
        data: data 参数。
    """
    try:
        client = get_core_client()
        result = await client.execute_skill(skill_id, data)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/executions/{execution_id}")
async def get_skill_execution(execution_id: str):
    """Get skill execution result.

    Args:
        execution_id: execution 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_skill_execution(execution_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}/executions")
async def list_skill_executions(
    skill_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get skill execution history.

    Args:
        skill_id: Skill ID。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.list_skill_executions(skill_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Memory Management ====================

@router.get("/memory/sessions")
async def list_sessions(
    status: Optional[str] = None,
    agent_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all sessions.

    Args:
        status: status 参数。
        agent_type: agent_type 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.list_sessions(status, agent_type, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/sessions")
async def create_session(session: dict):
    """Create a new session.

    Args:
        session: session 参数。
    """
    try:
        client = get_core_client()
        result = await client.create_session(session)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/memory/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details.

    Args:
        session_id: 会话 ID。
    """
    try:
        client = get_core_client()
        result = await client.get_session(session_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/memory/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete session.

    Args:
        session_id: 会话 ID。
    """
    try:
        client = get_core_client()
        result = await client.delete_session(session_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/memory/stats")
async def get_memory_stats():
    """Get memory statistics."""
    try:
        client = get_core_client()
        result = await client.get_memory_stats()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Session context and messages
@router.get("/memory/sessions/{session_id}/context")
async def get_session_context(session_id: str):
    """Get session context and messages.

    Args:
        session_id: 会话 ID。
    """
    try:
        client = get_core_client()
        result = await client.get_session_context(session_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/sessions/{session_id}/messages")
async def add_session_message(session_id: str, message: dict):
    """Add message to session.

    Args:
        session_id: 会话 ID。
        message: message 参数。
    """
    try:
        client = get_core_client()
        result = await client.add_session_message(session_id, message)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Memory search and management
@router.post("/memory/search")
async def search_memory(query: dict):
    """Search memory with vector similarity.

    Args:
        query: 查询。
    """
    try:
        client = get_core_client()
        result = await client.search_memory(query)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/cleanup")
async def cleanup_memory(params: Optional[dict] = None):
    """Clean up expired memories.

    Args:
        params: params 参数。
    """
    try:
        client = get_core_client()
        result = await client.cleanup_memory(params or {})
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/memory/export")
async def export_memory(
    format: Optional[str] = None,
    session_id: Optional[str] = None
):
    """Export memory data.

    Args:
        format: format 参数。
        session_id: 会话 ID。
    """
    try:
        client = get_core_client()
        result = await client.export_memory(format=format, session_id=session_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/import")
async def import_memory(data: dict):
    """Import memory data.

    Args:
        data: data 参数。
    """
    try:
        client = get_core_client()
        result = await client.import_memory(data)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Knowledge Management ====================

@router.get("/knowledge/collections")
async def list_collections(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all collections.

    Args:
        status: status 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.list_collections(status, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/knowledge/collections")
async def create_collection(collection: dict):
    """Create a new collection.

    Args:
        collection: collection 参数。
    """
    try:
        client = get_core_client()
        result = await client.create_collection(collection)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/knowledge/collections/{collection_id}")
async def get_collection(collection_id: str):
    """Get collection details.

    Args:
        collection_id: collection 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_collection(collection_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/knowledge/collections/{collection_id}")
async def update_collection(collection_id: str, updates: dict):
    """Update collection.

    Args:
        collection_id: collection 标识。
        updates: updates 参数。
    """
    try:
        client = get_core_client()
        result = await client.update_collection(collection_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/knowledge/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete collection.

    Args:
        collection_id: collection 标识。
    """
    try:
        client = get_core_client()
        result = await client.delete_collection(collection_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Collection reindex
@router.post("/knowledge/collections/{collection_id}/reindex")
async def reindex_collection(collection_id: str):
    """Rebuild collection index.

    Args:
        collection_id: collection 标识。
    """
    try:
        client = get_core_client()
        result = await client.reindex_collection(collection_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Document management
@router.post("/knowledge/documents")
async def upload_document(document: dict):
    """Upload document to knowledge base.

    Args:
        document: document 参数。
    """
    try:
        client = get_core_client()
        result = await client.upload_document(document)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/knowledge/documents/{document_id}")
async def get_document(document_id: str):
    """Get document status.

    Args:
        document_id: document 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_document(document_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/knowledge/collections/{collection_id}/documents")
async def list_collection_documents(
    collection_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List documents in collection.

    Args:
        collection_id: collection 标识。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.list_collection_documents(collection_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete document from knowledge base.

    Args:
        document_id: document 标识。
    """
    try:
        client = get_core_client()
        result = await client.delete_document(document_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Knowledge search
@router.post("/knowledge/search")
async def search_knowledge(query: dict):
    """Search/retrieve knowledge.

    Args:
        query: 查询。
    """
    try:
        client = get_core_client()
        result = await client.search_knowledge(query)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/knowledge/collections/{collection_id}/search/logs")
async def get_search_logs(
    collection_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get search logs for collection.

    Args:
        collection_id: collection 标识。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.get_search_logs(collection_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Adapter Management ====================

@router.get("/adapters")
async def list_adapters(
    provider: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all adapters.

    Args:
        provider: provider 参数。
        status: status 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.list_adapters(provider, status, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters")
async def create_adapter(adapter: dict):
    """Create a new adapter.

    Args:
        adapter: adapter 参数。
    """
    try:
        client = get_core_client()
        result = await client.create_adapter(adapter)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/adapters/{adapter_id}")
async def get_adapter(adapter_id: str):
    """Get adapter details.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/adapters/{adapter_id}")
async def update_adapter(adapter_id: str, updates: dict):
    """Update adapter.

    Args:
        adapter_id: adapter 标识。
        updates: updates 参数。
    """
    try:
        client = get_core_client()
        result = await client.update_adapter(adapter_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/adapters/{adapter_id}")
async def delete_adapter(adapter_id: str):
    """Delete adapter.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.delete_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters/{adapter_id}/test")
async def test_adapter(adapter_id: str):
    """Test adapter connection.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.test_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Adapter enable/disable
@router.post("/adapters/{adapter_id}/enable")
async def enable_adapter(adapter_id: str):
    """Enable adapter.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.enable_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters/{adapter_id}/disable")
async def disable_adapter(adapter_id: str):
    """Disable adapter.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.disable_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Model configuration
@router.get("/adapters/{adapter_id}/models")
async def get_adapter_models(adapter_id: str):
    """Get adapter model list.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_adapter_models(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters/{adapter_id}/models")
async def add_adapter_model(adapter_id: str, model: dict):
    """Add model configuration.

    Args:
        adapter_id: adapter 标识。
        model: 模型名。
    """
    try:
        client = get_core_client()
        result = await client.add_adapter_model(adapter_id, model)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/adapters/{adapter_id}/models/{model_name}")
async def update_adapter_model(adapter_id: str, model_name: str, model: dict):
    """Update model configuration.

    Args:
        adapter_id: adapter 标识。
        model_name: model_name 参数。
        model: 模型名。
    """
    try:
        client = get_core_client()
        result = await client.update_adapter_model(adapter_id, model_name, model)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/adapters/{adapter_id}/models/{model_name}")
async def delete_adapter_model(adapter_id: str, model_name: str):
    """Delete model configuration.

    Args:
        adapter_id: adapter 标识。
        model_name: model_name 参数。
    """
    try:
        client = get_core_client()
        result = await client.delete_adapter_model(adapter_id, model_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Adapter monitoring
@router.get("/adapters/{adapter_id}/stats")
async def get_adapter_stats(adapter_id: str):
    """Get adapter call statistics.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_adapter_stats(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/adapters/{adapter_id}/calls")
async def get_adapter_calls(
    adapter_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get adapter call history.

    Args:
        adapter_id: adapter 标识。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.get_adapter_calls(adapter_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/adapters/{adapter_id}/model-distribution")
async def get_adapter_model_distribution(adapter_id: str):
    """Get model call distribution.

    Args:
        adapter_id: adapter 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_adapter_model_distribution(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Harness Management ====================

@router.get("/harness/status")
async def get_harness_status():
    """Get harness status."""
    try:
        client = get_core_client()
        result = await client.get_harness_status()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/harness/config")
async def get_harness_config():
    """Get harness configuration."""
    try:
        client = get_core_client()
        result = await client.get_harness_config()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/harness/config")
async def update_harness_config(config: dict):
    """Update harness configuration.

    Args:
        config: config 参数。
    """
    try:
        client = get_core_client()
        result = await client.update_harness_config(config)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/harness/metrics")
async def get_harness_metrics():
    """Get harness metrics."""
    try:
        client = get_core_client()
        result = await client.get_harness_metrics()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/harness/logs")
async def get_harness_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    agent: Optional[str] = None
):
    """Get execution logs.

    Args:
        limit: 返回条数上限。
        offset: 分页偏移。
        status: status 参数。
        agent: agent 参数。
    """
    try:
        client = get_core_client()
        result = await client.get_harness_logs(limit, offset, status, agent)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/harness/hooks")
async def get_hooks():
    """Get all hooks."""
    try:
        client = get_core_client()
        result = await client.get_hooks()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/harness/hooks")
async def add_hook(hook: dict):
    """Add a hook.

    Args:
        hook: hook 参数。
    """
    try:
        client = get_core_client()
        result = await client.add_hook(hook)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/harness/hooks/{hook_id}")
async def delete_hook(hook_id: str):
    """Delete a hook.

    Args:
        hook_id: hook 标识。
    """
    try:
        client = get_core_client()
        result = await client.delete_hook(hook_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/harness/hooks/{hook_id}")
async def update_hook(hook_id: str, updates: dict):
    """Update a hook.

    Args:
        hook_id: hook 标识。
        updates: updates 参数。
    """
    try:
        client = get_core_client()
        result = await client.update_hook(hook_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Execution management
@router.get("/harness/executions/{execution_id}")
async def get_execution_detail(execution_id: str):
    """Get execution details.

    Args:
        execution_id: execution 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_execution_detail(execution_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Coordinator management
@router.get("/harness/coordinators")
async def list_coordinators(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all coordinators.

    Args:
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        result = await client.list_coordinators(limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/harness/coordinators")
async def create_coordinator(coordinator: dict):
    """Create a new coordinator.

    Args:
        coordinator: coordinator 参数。
    """
    try:
        client = get_core_client()
        result = await client.create_coordinator(coordinator)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/harness/coordinators/{coordinator_id}")
async def get_coordinator(coordinator_id: str):
    """Get coordinator details.

    Args:
        coordinator_id: coordinator 标识。
    """
    try:
        client = get_core_client()
        result = await client.get_coordinator(coordinator_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/harness/coordinators/{coordinator_id}")
async def update_coordinator(coordinator_id: str, updates: dict):
    """Update coordinator.

    Args:
        coordinator_id: coordinator 标识。
        updates: updates 参数。
    """
    try:
        client = get_core_client()
        result = await client.update_coordinator(coordinator_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/harness/coordinators/{coordinator_id}")
async def delete_coordinator(coordinator_id: str):
    """Delete coordinator.

    Args:
        coordinator_id: coordinator 标识。
    """
    try:
        client = get_core_client()
        result = await client.delete_coordinator(coordinator_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Feedback loop management
@router.get("/harness/feedback/config")
async def get_feedback_config():
    """Get feedback loop configuration."""
    try:
        client = get_core_client()
        result = await client.get_feedback_config()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/harness/feedback/config")
async def update_feedback_config(config: dict):
    """Update feedback loop configuration.

    Args:
        config: config 参数。
    """
    try:
        client = get_core_client()
        result = await client.update_feedback_config(config)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Tools ====================

@router.get("/tools")
async def list_tools(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    available_only: bool = False,
):
    """List all registered tools on the core layer.

    Args:
        limit: 返回条数上限。
        offset: 分页偏移。
        available_only: available_only 参数。
    """
    try:
        client = get_core_client()
        return await client.list_tools(limit=limit, offset=offset, available_only=available_only)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ── Gateway Admin (pairings / tokens) ──
# In-memory storage for gateway data (to be migrated to SQLite later)
_gateway_pairings: Dict[str, dict] = {}  # key = f"{channel}:{channel_user_id}"
_gateway_tokens: Dict[str, dict] = {}

def _pairing_key(channel: str, channel_user_id: str) -> str:
    return f"{channel}:{channel_user_id}"

@router.get("/gateway/pairings")
async def list_gateway_pairings(channel: Optional[str] = None, user_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    """列出 gateway_pairings。

    Args:
        channel: channel 参数。
        user_id: 用户 ID。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    items = list(_gateway_pairings.values())
    if channel:
        items = [p for p in items if p.get("channel") == channel]
    if user_id:
        items = [p for p in items if p.get("user_id") == user_id]
    total = len(items)
    items = items[offset:offset + limit]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/gateway/pairings")
async def upsert_gateway_pairing(body: dict):
    """upsert_gateway_pairing。

    Args:
        body: 请求体。
    """
    channel = body.get("channel", "")
    channel_user_id = body.get("channel_user_id", "")
    if not channel or not channel_user_id:
        raise HTTPException(status_code=400, detail="channel and channel_user_id are required")
    key = _pairing_key(channel, channel_user_id)
    existing = _gateway_pairings.get(key)
    now = time.time()
    pairing = {
        "id": existing["id"] if existing else f"gp_{secrets.token_hex(6)}",
        "channel": channel,
        "channel_user_id": channel_user_id,
        "user_id": body.get("user_id", ""),
        "session_id": body.get("session_id", "default"),
        "tenant_id": body.get("tenant_id"),
        "metadata": body.get("metadata"),
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
    }
    _gateway_pairings[key] = pairing
    return pairing


@router.delete("/gateway/pairings")
async def delete_gateway_pairing(channel: str, channel_user_id: str):
    """删除 gateway_pairing。

    Args:
        channel: channel 参数。
        channel_user_id: channel_user 标识。
    """
    key = _pairing_key(channel, channel_user_id)
    if key not in _gateway_pairings:
        raise HTTPException(status_code=404, detail="Pairing not found")
    del _gateway_pairings[key]
    return {"status": "deleted"}


@router.get("/gateway/tokens")
async def list_gateway_tokens(enabled: Optional[bool] = None, limit: int = 100, offset: int = 0):
    """列出 gateway_tokens。

    Args:
        enabled: 是否启用。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    items = list(_gateway_tokens.values())
    if enabled is not None:
        items = [t for t in items if bool(t.get("enabled")) == enabled]
    total = len(items)
    items = items[offset:offset + limit]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/gateway/tokens")
async def create_gateway_token(body: dict):
    """创建 gateway_token。

    Args:
        body: 请求体。
    """
    name = body.get("name", "default")
    raw_token = body.get("token", "")
    if not raw_token:
        raise HTTPException(status_code=400, detail="token is required")
    now = time.time()
    token_id = f"gt_{secrets.token_hex(8)}"
    token_data = {
        "id": token_id,
        "name": name,
        "token": raw_token,
        "tenant_id": body.get("tenant_id"),
        "enabled": body.get("enabled", True),
        "metadata": body.get("metadata"),
        "created_at": now,
    }
    _gateway_tokens[token_id] = token_data
    return token_data


@router.delete("/gateway/tokens/{token_id}")
async def delete_gateway_token(token_id: str):
    """删除 gateway_token。

    Args:
        token_id: token 标识。
    """
    if token_id not in _gateway_tokens:
        raise HTTPException(status_code=404, detail="Token not found")
    del _gateway_tokens[token_id]
    return {"status": "deleted", "token_id": token_id}


# ══════════════════════════════════════════════════════════════
# Diagrams Proxy — forward to core:8002
# ══════════════════════════════════════════════════════════════

import os as _os

_CORE_BASE = _os.getenv("AIPLAT_CORE_ENDPOINT", "http://localhost:8002")


@router.api_route("/diagrams{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_diagrams(request: Request, path: str = ""):
    """Proxy diagrams API to core server.

    Args:
        request: FastAPI Request。
        path: 路径。
    """
    async with httpx.AsyncClient(timeout=30) as client:
        url = f"{_CORE_BASE}/diagrams{path}"
        body = await request.body() if request.method in ("POST", "PUT") else None
        headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in ("host", "content-length")}
        resp = await client.request(
            request.method, url, content=body, headers=headers,
            params=dict(request.query_params),
        )
        from fastapi.responses import Response
        return Response(content=resp.content, status_code=resp.status_code,
                        headers=dict(resp.headers),
                        media_type=resp.headers.get("content-type"))
