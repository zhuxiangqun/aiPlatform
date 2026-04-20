"""
Core Layer Management API Router

This router provides unified API endpoints for core layer management.
It calls aiPlat-core layer's REST API (running on port 8002) for actual operations.

Architecture:
- aiPlat-management (this layer): Management system, unified API entry point
- aiPlat-core (8002): Core business layer, actual implementation
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
import httpx

from ..core_client import CoreAPIClient, CoreAPIClientConfig


router = APIRouter(prefix="/core", tags=["core"])

# Core API client configuration
_core_client: Optional[CoreAPIClient] = None


def get_core_client() -> CoreAPIClient:
    """Get or create the core API client."""
    global _core_client
    if _core_client is None:
        config = CoreAPIClientConfig(
            base_url="http://localhost:8002",
            timeout=30.0
        )
        _core_client = CoreAPIClient(config)
    return _core_client


# ==================== Runs (Platform Execution Contract) ====================


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    try:
        client = get_core_client()
        return await client.get_run(run_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/runs/{run_id}/events")
async def list_run_events(
    run_id: str,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
):
    try:
        client = get_core_client()
        return await client.list_run_events(run_id, after_seq=after_seq, limit=limit)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/runs/{run_id}/wait")
async def wait_run(run_id: str, body: dict):
    try:
        client = get_core_client()
        timeout_ms = int((body or {}).get("timeout_ms") or 30000)
        after_seq = int((body or {}).get("after_seq") or 0)
        return await client.wait_run(run_id, timeout_ms=timeout_ms, after_seq=after_seq)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, body: dict = None):
    try:
        client = get_core_client()
        return await client.cancel_run(run_id, body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: str):
    try:
        client = get_core_client()
        return await client.retry_run(run_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/runs/{run_id}/undo")
async def undo_run(run_id: str, body: dict = None):
    try:
        client = get_core_client()
        return await client.undo_run(run_id, body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Jobs / Cron (Roadmap-3) ====================


@router.get("/jobs")
async def list_jobs(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), enabled: Optional[bool] = None):
    try:
        client = get_core_client()
        return await client.list_jobs(limit=limit, offset=offset, enabled=enabled)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/jobs")
async def create_job(job: dict):
    try:
        client = get_core_client()
        return await client.create_job(job)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    try:
        client = get_core_client()
        return await client.get_job(job_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/jobs/{job_id}")
async def update_job(job_id: str, patch: dict):
    try:
        client = get_core_client()
        return await client.update_job(job_id, patch)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    try:
        client = get_core_client()
        return await client.delete_job(job_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Prompt Templates (platformization MVP) ====================


@router.get("/prompts")
async def list_prompt_templates(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    try:
        client = get_core_client()
        return await client.list_prompt_templates(limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/prompts/{template_id}")
async def get_prompt_template(template_id: str):
    try:
        client = get_core_client()
        return await client.get_prompt_template(str(template_id))
    except httpx.HTTPStatusError as e:
        # bubble up core status if available
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/prompts/{template_id}/versions")
async def list_prompt_template_versions(
    template_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    try:
        client = get_core_client()
        return await client.list_prompt_template_versions(str(template_id), limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/prompts/{template_id}/diff")
async def diff_prompt_template(template_id: str, from_version: Optional[str] = None, to_version: Optional[str] = None):
    try:
        client = get_core_client()
        params: Dict[str, Any] = {}
        if from_version:
            params["from_version"] = str(from_version)
        if to_version:
            params["to_version"] = str(to_version)
        return await client.prompt_template_diff(str(template_id), params=params)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/prompts/{template_id}/resolve")
async def resolve_prompt_template(template_id: str, tenant_id: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None):
    try:
        client = get_core_client()
        params: Dict[str, Any] = {}
        if tenant_id:
            params["tenant_id"] = str(tenant_id)
        if user_id:
            params["user_id"] = str(user_id)
        if session_id:
            params["session_id"] = str(session_id)
        return await client.prompt_template_resolve(str(template_id), params=params)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/prompts")
async def upsert_prompt_template(body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.upsert_prompt_template(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/prompts/{template_id}/rollback")
async def rollback_prompt_template(template_id: str, body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.rollback_prompt_template(str(template_id), body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/prompts/{template_id}/release")
async def release_prompt_template(template_id: str, body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.prompt_template_release(str(template_id), body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/prompts/{template_id}/release/rollback")
async def rollback_prompt_template_release(template_id: str, body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.prompt_template_release_rollback(str(template_id), body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/prompts/{template_id}")
async def delete_prompt_template(
    template_id: str,
    require_approval: bool = True,
    approval_request_id: Optional[str] = None,
    details: Optional[str] = None,
):
    try:
        client = get_core_client()
        return await client.delete_prompt_template(
            str(template_id), require_approval=bool(require_approval), approval_request_id=approval_request_id, details=details
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Learning / Releases / Approvals (Phase 6) ====================


@router.get("/learning/artifacts")
async def list_learning_artifacts(
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    try:
        client = get_core_client()
        return await client.list_learning_artifacts(
            target_type=target_type,
            target_id=target_id,
            kind=kind,
            status=status,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
            offset=offset,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/learning/artifacts/{artifact_id}")
async def get_learning_artifact(artifact_id: str):
    try:
        client = get_core_client()
        return await client.get_learning_artifact(str(artifact_id))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/artifacts/{artifact_id}/status")
async def set_learning_artifact_status(artifact_id: str, body: Dict[str, Any]):
    try:
        client = get_core_client()
        status = (body or {}).get("status")
        if not isinstance(status, str) or not status:
            raise HTTPException(status_code=400, detail="missing_status")
        metadata_update = (body or {}).get("metadata_update") if isinstance((body or {}).get("metadata_update"), dict) else {}
        return await client.set_learning_artifact_status(str(artifact_id), status=str(status), metadata_update=metadata_update)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/autocapture")
async def autocapture_learning(body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.autocapture(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/autocapture/to_prompt_revision")
async def autocapture_to_prompt_revision(body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.autocapture_to_prompt_revision(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/autocapture/to_skill_evolution")
async def autocapture_to_skill_evolution(body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.autocapture_to_skill_evolution(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/releases/{candidate_id}/publish")
async def publish_release_candidate(candidate_id: str, body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.publish_release_candidate(str(candidate_id), body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/releases/{candidate_id}/rollback")
async def rollback_release_candidate(candidate_id: str, body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.rollback_release_candidate(str(candidate_id), body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/releases/expire")
async def expire_releases(body: Dict[str, Any] = None):
    try:
        client = get_core_client()
        return await client.expire_releases(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/learning/rollouts")
async def list_release_rollouts(target_type: Optional[str] = None, target_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    try:
        client = get_core_client()
        return await client.list_release_rollouts(target_type=target_type, target_id=target_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/learning/rollouts")
async def upsert_release_rollout(body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.upsert_release_rollout(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/learning/rollouts")
async def delete_release_rollout(target_type: str = Query(...), target_id: str = Query(...)):
    try:
        client = get_core_client()
        return await client.delete_release_rollout({"target_type": str(target_type), "target_id": str(target_id)})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/releases/{candidate_id}/metrics/snapshots")
async def add_release_metric_snapshot(candidate_id: str, body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.add_release_metric_snapshot(str(candidate_id), body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/learning/releases/{candidate_id}/metrics/snapshots")
async def list_release_metric_snapshots(candidate_id: str, metric_key: Optional[str] = None, limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    try:
        client = get_core_client()
        return await client.list_release_metric_snapshots(str(candidate_id), metric_key=metric_key, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/auto-rollback/regression")
async def auto_rollback_regression(body: Dict[str, Any]):
    try:
        client = get_core_client()
        return await client.auto_rollback_regression(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/approvals/cleanup-rollback-approvals")
async def cleanup_rollback_approvals(body: Dict[str, Any] = None):
    try:
        client = get_core_client()
        return await client.cleanup_rollback_approvals(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/jobs/{job_id}/enable")
async def enable_job(job_id: str):
    try:
        client = get_core_client()
        return await client.enable_job(job_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/jobs/{job_id}/disable")
async def disable_job(job_id: str):
    try:
        client = get_core_client()
        return await client.disable_job(job_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/jobs/{job_id}/run")
async def run_job(job_id: str):
    try:
        client = get_core_client()
        return await client.run_job(job_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/jobs/{job_id}/runs")
async def list_job_runs(job_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    try:
        client = get_core_client()
        return await client.list_job_runs(job_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/jobs/dlq")
async def list_job_dlq(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    job_id: Optional[str] = None,
):
    try:
        client = get_core_client()
        return await client.list_job_delivery_dlq(status=status, job_id=job_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/jobs/dlq/{dlq_id}/retry")
async def retry_job_dlq(dlq_id: str):
    try:
        client = get_core_client()
        return await client.retry_job_delivery_dlq(dlq_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/jobs/dlq/{dlq_id}")
async def delete_job_dlq(dlq_id: str):
    try:
        client = get_core_client()
        return await client.delete_job_delivery_dlq(dlq_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Gateway Admin (pairings / tokens) ====================


@router.get("/gateway/pairings")
async def list_gateway_pairings(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
):
    try:
        client = get_core_client()
        return await client.list_gateway_pairings(channel=channel, user_id=user_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/gateway/pairings")
async def upsert_gateway_pairing(body: dict):
    try:
        client = get_core_client()
        return await client.upsert_gateway_pairing(body)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/gateway/pairings")
async def delete_gateway_pairing(channel: str, channel_user_id: str):
    try:
        client = get_core_client()
        return await client.delete_gateway_pairing(channel=channel, channel_user_id=channel_user_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/gateway/tokens")
async def list_gateway_tokens(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), enabled: Optional[bool] = None):
    try:
        client = get_core_client()
        return await client.list_gateway_tokens(enabled=enabled, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/gateway/tokens")
async def create_gateway_token(body: dict):
    try:
        client = get_core_client()
        return await client.create_gateway_token(body)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/gateway/tokens/{token_id}")
async def delete_gateway_token(token_id: str):
    try:
        client = get_core_client()
        return await client.delete_gateway_token(token_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Agent Management ====================

@router.get("/agents")
async def list_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all agents."""
    try:
        client = get_core_client()
        result = await client.list_agents(agent_type, status, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents")
async def create_agent(agent: dict):
    """Create a new agent."""
    try:
        client = get_core_client()
        result = await client.create_agent(agent)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details."""
    try:
        client = get_core_client()
        result = await client.get_agent(agent_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, updates: dict):
    """Update agent."""
    try:
        client = get_core_client()
        result = await client.update_agent(agent_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete agent."""
    try:
        client = get_core_client()
        result = await client.delete_agent(agent_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents/{agent_id}/start")
async def start_agent(agent_id: str):
    """Start agent."""
    try:
        client = get_core_client()
        result = await client.start_agent(agent_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Stop agent."""
    try:
        client = get_core_client()
        result = await client.stop_agent(agent_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Agent skill binding
@router.get("/agents/{agent_id}/skills")
async def get_agent_skills(agent_id: str):
    """Get skills bound to agent."""
    try:
        client = get_core_client()
        result = await client.get_agent_skills(agent_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents/{agent_id}/skills")
async def bind_agent_skills(agent_id: str, data: dict):
    """Bind skills to agent."""
    try:
        client = get_core_client()
        result = await client.bind_agent_skills(agent_id, data.get("skill_ids", []))
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/agents/{agent_id}/skills/{skill_id}")
async def unbind_agent_skill(agent_id: str, skill_id: str):
    """Unbind skill from agent."""
    try:
        client = get_core_client()
        result = await client.unbind_agent_skill(agent_id, skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Agent tool binding
@router.get("/agents/{agent_id}/tools")
async def get_agent_tools(agent_id: str):
    """Get tools bound to agent."""
    try:
        client = get_core_client()
        result = await client.get_agent_tools(agent_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/agents/{agent_id}/tools")
async def bind_agent_tools(agent_id: str, data: dict):
    """Bind tools to agent."""
    try:
        client = get_core_client()
        result = await client.bind_agent_tools(agent_id, data.get("tool_ids", []))
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/agents/{agent_id}/tools/{tool_id}")
async def unbind_agent_tool(agent_id: str, tool_id: str):
    """Unbind tool from agent."""
    try:
        client = get_core_client()
        result = await client.unbind_agent_tool(agent_id, tool_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Agent execution
@router.post("/agents/{agent_id}/execute")
async def execute_agent(agent_id: str, data: dict):
    """Execute agent with input."""
    try:
        client = get_core_client()
        result = await client.execute_agent(agent_id, data)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/agents/executions/{execution_id}")
async def get_execution(execution_id: str):
    """Get execution details."""
    try:
        client = get_core_client()
        result = await client.get_execution(execution_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Agent execution history
@router.get("/agents/{agent_id}/history")
async def get_agent_history(
    agent_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get agent execution history."""
    try:
        client = get_core_client()
        result = await client.get_agent_history(agent_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# ==================== Learning / Release Management (Phase 6) ====================


@router.get("/learning/artifacts")
async def list_learning_artifacts(
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    try:
        client = get_core_client()
        return await client.list_learning_artifacts(
            target_type=target_type,
            target_id=target_id,
            kind=kind,
            status=status,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
            offset=offset,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/learning/artifacts/{artifact_id}")
async def get_learning_artifact(artifact_id: str):
    try:
        client = get_core_client()
        return await client.get_learning_artifact(artifact_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/artifacts/{artifact_id}/status")
async def set_learning_artifact_status(artifact_id: str, body: dict):
    try:
        client = get_core_client()
        return await client.set_learning_artifact_status(
            artifact_id,
            status=str((body or {}).get("status") or ""),
            metadata_update=(body or {}).get("metadata_update") if isinstance((body or {}).get("metadata_update"), dict) else {},
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/releases/{candidate_id}/publish")
async def publish_release_candidate(candidate_id: str, body: dict):
    try:
        client = get_core_client()
        return await client.publish_release_candidate(candidate_id, body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/releases/{candidate_id}/rollback")
async def rollback_release_candidate(candidate_id: str, body: dict):
    try:
        client = get_core_client()
        return await client.rollback_release_candidate(candidate_id, body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/releases/expire")
async def expire_releases(body: dict):
    try:
        client = get_core_client()
        return await client.expire_releases(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/auto-rollback/regression")
async def auto_rollback_regression(body: dict):
    try:
        client = get_core_client()
        return await client.auto_rollback_regression(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/approvals/cleanup-rollback-approvals")
async def cleanup_rollback_approvals(body: dict):
    try:
        client = get_core_client()
        return await client.cleanup_rollback_approvals(body or {})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/learning/autocapture/to_prompt_revision")
async def autocapture_to_prompt_revision(body: dict):
    try:
        client = get_core_client()
        return await client.autocapture_to_prompt_revision(body or {})
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
    try:
        client = get_core_client()
        return await client.list_pending_approvals(user_id=user_id, order_by=order_by, order_dir=order_dir, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/approvals/{request_id}")
async def get_approval_request(request_id: str):
    try:
        client = get_core_client()
        return await client.get_approval_request(request_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/approvals/{request_id}/approve")
async def approve_approval_request(request_id: str, body: dict):
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
    """List all skills."""
    try:
        client = get_core_client()
        result = await client.list_skills(category=category, status=status, enabled_only=enabled_only, limit=limit, offset=offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills")
async def create_skill(skill: dict):
    """Create a new skill."""
    try:
        client = get_core_client()
        result = await client.create_skill(skill)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Get skill details."""
    try:
        client = get_core_client()
        result = await client.get_skill(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, updates: dict):
    """Update skill."""
    try:
        client = get_core_client()
        result = await client.update_skill(skill_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, delete_files: bool = False):
    """Delete skill (default soft delete; delete_files=true for hard delete)."""
    try:
        client = get_core_client()
        result = await client.delete_skill(skill_id, delete_files=delete_files)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/enable")
async def enable_skill(skill_id: str):
    """Enable skill."""
    try:
        client = get_core_client()
        result = await client.enable_skill(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/disable")
async def disable_skill(skill_id: str):
    """Disable skill."""
    try:
        client = get_core_client()
        result = await client.disable_skill(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/restore")
async def restore_skill(skill_id: str):
    """Restore a deprecated skill."""
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
    """Enable MCP server."""
    try:
        client = get_core_client()
        return await client.enable_mcp_server(server_name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/mcp/servers/{server_name}/disable")
async def disable_mcp_server(server_name: str):
    """Disable MCP server."""
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
    try:
        client = get_core_client()
        return await client.list_workspace_skills(category, status, enabled_only=enabled_only, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills")
async def create_workspace_skill(payload: dict):
    try:
        client = get_core_client()
        return await client.create_workspace_skill(payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}")
async def get_workspace_skill(skill_id: str):
    try:
        client = get_core_client()
        return await client.get_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/workspace/skills/{skill_id}")
async def update_workspace_skill(skill_id: str, payload: dict):
    try:
        client = get_core_client()
        return await client.update_workspace_skill(skill_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/execute")
async def execute_workspace_skill(skill_id: str, payload: dict):
    try:
        client = get_core_client()
        return await client.execute_workspace_skill(skill_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/enable")
async def enable_workspace_skill(skill_id: str):
    try:
        client = get_core_client()
        return await client.enable_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/disable")
async def disable_workspace_skill(skill_id: str):
    try:
        client = get_core_client()
        return await client.disable_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/restore")
async def restore_workspace_skill(skill_id: str):
    try:
        client = get_core_client()
        return await client.restore_workspace_skill(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/skills/{skill_id}")
async def delete_workspace_skill(skill_id: str, delete_files: bool = False):
    try:
        client = get_core_client()
        return await client.delete_workspace_skill(skill_id, delete_files=delete_files)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents")
async def list_workspace_agents(
    type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    try:
        client = get_core_client()
        return await client.list_workspace_agents(type, status, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents")
async def create_workspace_agent(payload: dict):
    try:
        client = get_core_client()
        return await client.create_workspace_agent(payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}")
async def get_workspace_agent(agent_id: str):
    try:
        client = get_core_client()
        return await client.get_workspace_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/workspace/agents/{agent_id}")
async def update_workspace_agent(agent_id: str, payload: dict):
    try:
        client = get_core_client()
        return await client.update_workspace_agent(agent_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}")
async def delete_workspace_agent(agent_id: str):
    try:
        client = get_core_client()
        return await client.delete_workspace_agent(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/execute")
async def execute_workspace_agent(agent_id: str, payload: dict):
    try:
        client = get_core_client()
        return await client.execute_workspace_agent(agent_id, payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/skills")
async def get_workspace_agent_skills(agent_id: str):
    try:
        client = get_core_client()
        return await client.get_workspace_agent_skills(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/skills")
async def bind_workspace_agent_skills(agent_id: str, payload: dict):
    try:
        client = get_core_client()
        skill_ids = list(payload.get("skill_ids") or [])
        return await client.bind_workspace_agent_skills(agent_id, skill_ids)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}/skills/{skill_id}")
async def unbind_workspace_agent_skill(agent_id: str, skill_id: str):
    try:
        client = get_core_client()
        return await client.unbind_workspace_agent_skill(agent_id, skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/tools")
async def get_workspace_agent_tools(agent_id: str):
    try:
        client = get_core_client()
        return await client.get_workspace_agent_tools(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/tools")
async def bind_workspace_agent_tools(agent_id: str, payload: dict):
    try:
        client = get_core_client()
        tool_ids = list(payload.get("tool_ids") or [])
        return await client.bind_workspace_agent_tools(agent_id, tool_ids)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/workspace/agents/{agent_id}/tools/{tool_id}")
async def unbind_workspace_agent_tool(agent_id: str, tool_id: str):
    try:
        client = get_core_client()
        return await client.unbind_workspace_agent_tool(agent_id, tool_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/history")
async def get_workspace_agent_history(agent_id: str, limit: int = 100, offset: int = 0):
    try:
        client = get_core_client()
        return await client.get_workspace_agent_history(agent_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/agents/{agent_id}/versions")
async def get_workspace_agent_versions(agent_id: str):
    try:
        client = get_core_client()
        return await client.get_workspace_agent_versions(agent_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/versions")
async def create_workspace_agent_version(agent_id: str, payload: dict):
    try:
        client = get_core_client()
        return await client.create_workspace_agent_version(agent_id, str((payload or {}).get("changes", "")))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/agents/{agent_id}/versions/{version}/rollback")
async def rollback_workspace_agent_version(agent_id: str, version: str):
    try:
        client = get_core_client()
        return await client.rollback_workspace_agent_version(agent_id, version)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}/executions")
async def list_workspace_skill_executions(skill_id: str, limit: int = 100, offset: int = 0):
    try:
        client = get_core_client()
        return await client.list_workspace_skill_executions(skill_id, limit=limit, offset=offset)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}/versions")
async def get_workspace_skill_versions(skill_id: str):
    try:
        client = get_core_client()
        return await client.get_workspace_skill_versions(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/skills/{skill_id}/active-version")
async def get_workspace_skill_active_version(skill_id: str):
    try:
        client = get_core_client()
        return await client.get_workspace_skill_active_version(skill_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/skills/{skill_id}/versions/{version}/rollback")
async def rollback_workspace_skill_version(skill_id: str, version: str):
    try:
        client = get_core_client()
        return await client.rollback_workspace_skill_version(skill_id, version)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/workspace/mcp/servers")
async def list_workspace_mcp_servers():
    try:
        client = get_core_client()
        return await client.list_workspace_mcp_servers()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/mcp/servers/{server_name}/enable")
async def enable_workspace_mcp_server(server_name: str):
    try:
        client = get_core_client()
        return await client.enable_workspace_mcp_server(server_name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/workspace/mcp/servers/{server_name}/disable")
async def disable_workspace_mcp_server(server_name: str):
    try:
        client = get_core_client()
        return await client.disable_workspace_mcp_server(server_name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}/agents")
async def get_skill_agents(skill_id: str):
    """Get agents bound to this skill."""
    try:
        client = get_core_client()
        result = await client.get_skill_agents(skill_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}/binding-stats")
async def get_skill_binding_stats(skill_id: str):
    """Get skill binding statistics."""
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
    """Get skill version list."""
    try:
        client = get_core_client()
        result = await client.get_skill_versions(skill_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/{skill_id}/versions/{version}")
async def get_skill_version(skill_id: str, version: str):
    """Get specific skill version."""
    try:
        client = get_core_client()
        result = await client.get_skill_version(skill_id, version)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/skills/{skill_id}/versions/{version}/rollback")
async def rollback_skill_version(skill_id: str, version: str):
    """Rollback skill to specific version."""
    try:
        client = get_core_client()
        result = await client.rollback_skill_version(skill_id, version)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Skill execution
@router.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, data: dict):
    """Execute skill with input."""
    try:
        client = get_core_client()
        result = await client.execute_skill(skill_id, data)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/skills/executions/{execution_id}")
async def get_skill_execution(execution_id: str):
    """Get skill execution result."""
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
    """Get skill execution history."""
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
    """List all sessions."""
    try:
        client = get_core_client()
        result = await client.list_sessions(status, agent_type, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/sessions")
async def create_session(session: dict):
    """Create a new session."""
    try:
        client = get_core_client()
        result = await client.create_session(session)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/memory/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    try:
        client = get_core_client()
        result = await client.get_session(session_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/memory/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete session."""
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
    """Get session context and messages."""
    try:
        client = get_core_client()
        result = await client.get_session_context(session_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/sessions/{session_id}/messages")
async def add_session_message(session_id: str, message: dict):
    """Add message to session."""
    try:
        client = get_core_client()
        result = await client.add_session_message(session_id, message)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Memory search and management
@router.post("/memory/search")
async def search_memory(query: dict):
    """Search memory with vector similarity."""
    try:
        client = get_core_client()
        result = await client.search_memory(query)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/cleanup")
async def cleanup_memory(params: Optional[dict] = None):
    """Clean up expired memories."""
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
    """Export memory data."""
    try:
        client = get_core_client()
        result = await client.export_memory(format=format, session_id=session_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/memory/import")
async def import_memory(data: dict):
    """Import memory data."""
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
    """List all collections."""
    try:
        client = get_core_client()
        result = await client.list_collections(status, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/knowledge/collections")
async def create_collection(collection: dict):
    """Create a new collection."""
    try:
        client = get_core_client()
        result = await client.create_collection(collection)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/knowledge/collections/{collection_id}")
async def get_collection(collection_id: str):
    """Get collection details."""
    try:
        client = get_core_client()
        result = await client.get_collection(collection_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/knowledge/collections/{collection_id}")
async def update_collection(collection_id: str, updates: dict):
    """Update collection."""
    try:
        client = get_core_client()
        result = await client.update_collection(collection_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/knowledge/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete collection."""
    try:
        client = get_core_client()
        result = await client.delete_collection(collection_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Collection reindex
@router.post("/knowledge/collections/{collection_id}/reindex")
async def reindex_collection(collection_id: str):
    """Rebuild collection index."""
    try:
        client = get_core_client()
        result = await client.reindex_collection(collection_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Document management
@router.post("/knowledge/documents")
async def upload_document(document: dict):
    """Upload document to knowledge base."""
    try:
        client = get_core_client()
        result = await client.upload_document(document)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/knowledge/documents/{document_id}")
async def get_document(document_id: str):
    """Get document status."""
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
    """List documents in collection."""
    try:
        client = get_core_client()
        result = await client.list_collection_documents(collection_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete document from knowledge base."""
    try:
        client = get_core_client()
        result = await client.delete_document(document_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Knowledge search
@router.post("/knowledge/search")
async def search_knowledge(query: dict):
    """Search/retrieve knowledge."""
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
    """Get search logs for collection."""
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
    """List all adapters."""
    try:
        client = get_core_client()
        result = await client.list_adapters(provider, status, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters")
async def create_adapter(adapter: dict):
    """Create a new adapter."""
    try:
        client = get_core_client()
        result = await client.create_adapter(adapter)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/adapters/{adapter_id}")
async def get_adapter(adapter_id: str):
    """Get adapter details."""
    try:
        client = get_core_client()
        result = await client.get_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/adapters/{adapter_id}")
async def update_adapter(adapter_id: str, updates: dict):
    """Update adapter."""
    try:
        client = get_core_client()
        result = await client.update_adapter(adapter_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/adapters/{adapter_id}")
async def delete_adapter(adapter_id: str):
    """Delete adapter."""
    try:
        client = get_core_client()
        result = await client.delete_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters/{adapter_id}/test")
async def test_adapter(adapter_id: str):
    """Test adapter connection."""
    try:
        client = get_core_client()
        result = await client.test_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Adapter enable/disable
@router.post("/adapters/{adapter_id}/enable")
async def enable_adapter(adapter_id: str):
    """Enable adapter."""
    try:
        client = get_core_client()
        result = await client.enable_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters/{adapter_id}/disable")
async def disable_adapter(adapter_id: str):
    """Disable adapter."""
    try:
        client = get_core_client()
        result = await client.disable_adapter(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Model configuration
@router.get("/adapters/{adapter_id}/models")
async def get_adapter_models(adapter_id: str):
    """Get adapter model list."""
    try:
        client = get_core_client()
        result = await client.get_adapter_models(adapter_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/adapters/{adapter_id}/models")
async def add_adapter_model(adapter_id: str, model: dict):
    """Add model configuration."""
    try:
        client = get_core_client()
        result = await client.add_adapter_model(adapter_id, model)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/adapters/{adapter_id}/models/{model_name}")
async def update_adapter_model(adapter_id: str, model_name: str, model: dict):
    """Update model configuration."""
    try:
        client = get_core_client()
        result = await client.update_adapter_model(adapter_id, model_name, model)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/adapters/{adapter_id}/models/{model_name}")
async def delete_adapter_model(adapter_id: str, model_name: str):
    """Delete model configuration."""
    try:
        client = get_core_client()
        result = await client.delete_adapter_model(adapter_id, model_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Adapter monitoring
@router.get("/adapters/{adapter_id}/stats")
async def get_adapter_stats(adapter_id: str):
    """Get adapter call statistics."""
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
    """Get adapter call history."""
    try:
        client = get_core_client()
        result = await client.get_adapter_calls(adapter_id, limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/adapters/{adapter_id}/model-distribution")
async def get_adapter_model_distribution(adapter_id: str):
    """Get model call distribution."""
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
    """Update harness configuration."""
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
    """Get execution logs."""
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
    """Add a hook."""
    try:
        client = get_core_client()
        result = await client.add_hook(hook)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/harness/hooks/{hook_id}")
async def delete_hook(hook_id: str):
    """Delete a hook."""
    try:
        client = get_core_client()
        result = await client.delete_hook(hook_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/harness/hooks/{hook_id}")
async def update_hook(hook_id: str, updates: dict):
    """Update a hook."""
    try:
        client = get_core_client()
        result = await client.update_hook(hook_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


# Execution management
@router.get("/harness/executions/{execution_id}")
async def get_execution_detail(execution_id: str):
    """Get execution details."""
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
    """List all coordinators."""
    try:
        client = get_core_client()
        result = await client.list_coordinators(limit, offset)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.post("/harness/coordinators")
async def create_coordinator(coordinator: dict):
    """Create a new coordinator."""
    try:
        client = get_core_client()
        result = await client.create_coordinator(coordinator)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/harness/coordinators/{coordinator_id}")
async def get_coordinator(coordinator_id: str):
    """Get coordinator details."""
    try:
        client = get_core_client()
        result = await client.get_coordinator(coordinator_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/harness/coordinators/{coordinator_id}")
async def update_coordinator(coordinator_id: str, updates: dict):
    """Update coordinator."""
    try:
        client = get_core_client()
        result = await client.update_coordinator(coordinator_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.delete("/harness/coordinators/{coordinator_id}")
async def delete_coordinator(coordinator_id: str):
    """Delete coordinator."""
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
    """Update feedback loop configuration."""
    try:
        client = get_core_client()
        result = await client.update_feedback_config(config)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")
