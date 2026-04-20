"""
Core Layer API Client

HTTP client for calling aiPlat-core layer API.
"""

import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from management.request_context import get_forward_headers


@dataclass
class CoreAPIClientConfig:
    """Configuration for Core API client."""
    base_url: str = "http://localhost:8002"
    timeout: float = 30.0
    transport: Optional[httpx.BaseTransport] = None


class CoreAPIError(Exception):
    """
    Structured downstream error from aiPlat-core.

    We keep the original HTTP status code and JSON payload (if any) so that
    aiPlat-management can transparently proxy core's gate/approval envelopes.
    """

    def __init__(self, status_code: int, payload: Any):
        super().__init__(f"Core API error: status={status_code}")
        self.status_code = int(status_code)
        self.payload = payload


class CoreAPIClient:
    """HTTP client for aiPlat-core API."""
    
    def __init__(self, config: Optional[CoreAPIClientConfig] = None):
        self.config = config or CoreAPIClientConfig()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            transport=self.config.transport,
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to core API."""
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                transport=self.config.transport,
            )
        
        # PR-01: forward tenant/actor identity headers (best-effort).
        try:
            fh = get_forward_headers()
            if fh:
                h0 = kwargs.get("headers") if isinstance(kwargs.get("headers"), dict) else {}
                h = dict(h0)
                for k, v in fh.items():
                    h.setdefault(k, v)
                kwargs["headers"] = h
        except Exception:
            pass

        response = await self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                payload: Any = response.json()
            except Exception:
                payload = {"detail": response.text}
            raise CoreAPIError(status_code=response.status_code, payload=payload)
        return response.json()

    async def _request_raw(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make HTTP request to core API and return the raw response (for files/streams)."""
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                transport=self.config.transport,
            )

        # PR-01: forward tenant/actor identity headers (best-effort).
        try:
            fh = get_forward_headers()
            if fh:
                h0 = kwargs.get("headers") if isinstance(kwargs.get("headers"), dict) else {}
                h = dict(h0)
                for k, v in fh.items():
                    h.setdefault(k, v)
                kwargs["headers"] = h
        except Exception:
            pass

        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                payload: Any = resp.json()
            except Exception:
                payload = {"detail": resp.text}
            raise CoreAPIError(status_code=resp.status_code, payload=payload)
        return resp

    # ===== Trace / Persistence (ExecutionStore) =====

    async def list_traces(self, limit: int = 100, offset: int = 0, status: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return await self._request("GET", "/api/core/traces", params=params)

    async def get_trace(self, trace_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/traces/{trace_id}")

    async def get_trace_by_execution(self, execution_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/executions/{execution_id}/trace")

    async def list_executions_by_trace(self, trace_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        return await self._request("GET", f"/api/core/traces/{trace_id}/executions", params=params)

    async def list_syscall_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
        error_contains: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        approval_request_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if trace_id:
            params["trace_id"] = trace_id
        if run_id:
            params["run_id"] = run_id
        if kind:
            params["kind"] = kind
        if name:
            params["name"] = name
        if status:
            params["status"] = status
        if error_contains:
            params["error_contains"] = error_contains
        if target_type:
            params["target_type"] = target_type
        if target_id:
            params["target_id"] = target_id
        if approval_request_id:
            params["approval_request_id"] = approval_request_id
        if span_id:
            params["span_id"] = span_id
        return await self._request("GET", "/api/core/syscalls/events", params=params)

    async def get_syscall_stats(
        self,
        *,
        window_hours: int = 24,
        top_n: int = 10,
        kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"window_hours": window_hours, "top_n": top_n}
        if kind:
            params["kind"] = kind
        return await self._request("GET", "/api/core/syscalls/stats", params=params)

    # ===== Change Control (derived) =====

    async def list_change_controls(self, *, limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        if tenant_id:
            params["tenant_id"] = str(tenant_id)
        return await self._request("GET", "/api/core/change-control/changes", params=params)

    async def get_change_control(
        self,
        change_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        if tenant_id:
            params["tenant_id"] = str(tenant_id)
        return await self._request("GET", f"/api/core/change-control/changes/{change_id}", params=params)

    async def autosmoke_change_control(self, change_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/change-control/changes/{change_id}/autosmoke", json={})

    # ===== Runs (Platform execution contract) =====

    async def get_run(self, run_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/runs/{run_id}")

    async def list_run_events(self, run_id: str, *, after_seq: int = 0, limit: int = 200) -> Dict[str, Any]:
        params: Dict[str, Any] = {"after_seq": int(after_seq), "limit": int(limit)}
        return await self._request("GET", f"/api/core/runs/{run_id}/events", params=params)

    async def wait_run(self, run_id: str, *, timeout_ms: int = 30000, after_seq: int = 0) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/core/runs/{run_id}/wait",
            json={"timeout_ms": int(timeout_ms), "after_seq": int(after_seq)},
        )

    # ===== Diagnostics: E2E smoke =====
    async def run_e2e_smoke(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/diagnostics/e2e/smoke", json=body or {})

    # ===== Adapters =====

    async def list_adapters(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        return await self._request("GET", "/api/core/adapters", params=params)

    async def create_adapter(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/adapters", json=body or {})

    async def test_adapter(self, adapter_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/adapters/{adapter_id}/test", json=body or {})

    async def add_adapter_model(self, adapter_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/adapters/{adapter_id}/models", json=body or {})

    async def update_adapter(self, adapter_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("PUT", f"/api/core/adapters/{adapter_id}", json=body or {})

    # ===== Core Onboarding =====

    async def get_onboarding_state(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/core/onboarding/state")

    async def set_default_llm(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/onboarding/default-llm", json=body or {})

    async def init_tenant(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/onboarding/init-tenant", json=body or {})

    async def set_autosmoke(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/onboarding/autosmoke", json=body or {})

    async def get_secrets_status(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/core/onboarding/secrets/status")

    async def migrate_secrets(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/onboarding/secrets/migrate", json=body or {})

    async def set_strong_gate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/onboarding/strong-gate", json=body or {})

    async def set_exec_backend(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/onboarding/exec-backend", json=body or {})

    async def set_trusted_skill_keys(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/onboarding/trusted-skill-keys", json=body or {})

    # ===== Tenant Policies =====

    async def get_tenant_policy(self, tenant_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/policies/tenants/{tenant_id}")

    # ===== Diagnostics: context/prompt =====

    async def get_context_config(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/core/diagnostics/context/config")

    async def diagnostics_prompt_assemble(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/diagnostics/prompt/assemble", json=body or {})

    # ===== Prompt Templates =====

    async def list_prompt_templates(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        return await self._request("GET", "/api/core/prompts", params={"limit": int(limit), "offset": int(offset)})

    async def get_prompt_template(self, template_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/prompts/{template_id}")

    async def list_prompt_template_versions(self, template_id: str, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/core/prompts/{template_id}/versions",
            params={"limit": int(limit), "offset": int(offset)},
        )

    async def upsert_prompt_template(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/prompts", json=body or {})

    async def rollback_prompt_template(self, template_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/prompts/{template_id}/rollback", json=body or {})

    async def delete_prompt_template(self, template_id: str, *, require_approval: bool = True, approval_request_id: Optional[str] = None, details: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"require_approval": bool(require_approval)}
        if approval_request_id:
            params["approval_request_id"] = str(approval_request_id)
        if details:
            params["details"] = str(details)
        return await self._request("DELETE", f"/api/core/prompts/{template_id}", params=params)

    # ===== Repo diagnostics =====

    async def repo_changeset_preview(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/diagnostics/repo/changeset/preview", json=body or {})

    async def repo_changeset_record(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/diagnostics/repo/changeset/record", json=body or {})

    async def repo_tests_run(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/diagnostics/repo/tests/run", json=body or {})

    async def repo_staged_preview(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/diagnostics/repo/staged/preview", json=body or {})

    async def prompt_template_diff(self, template_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/prompts/{template_id}/diff", params=params or {})

    async def exec_backends(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/core/diagnostics/exec/backends")

    # ===== Jobs / Cron (Roadmap-3) =====

    async def list_jobs(self, *, limit: int = 100, offset: int = 0, enabled: Optional[bool] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if enabled is not None:
            params["enabled"] = bool(enabled)
        return await self._request("GET", "/api/core/jobs", params=params)

    async def create_job(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/jobs", json=data)

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/jobs/{job_id}")

    async def update_job(self, job_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("PUT", f"/api/core/jobs/{job_id}", json=data)

    async def delete_job(self, job_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/api/core/jobs/{job_id}")

    async def enable_job(self, job_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/jobs/{job_id}/enable", json={})

    async def disable_job(self, job_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/jobs/{job_id}/disable", json={})

    async def run_job(self, job_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/jobs/{job_id}/run", json={})

    async def list_job_runs(self, job_id: str, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        return await self._request("GET", f"/api/core/jobs/{job_id}/runs", params=params)

    async def list_job_delivery_dlq(self, *, status: Optional[str] = None, job_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if job_id:
            params["job_id"] = job_id
        return await self._request("GET", "/api/core/jobs/dlq", params=params)

    async def retry_job_delivery_dlq(self, dlq_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/jobs/dlq/{dlq_id}/retry", json={})

    async def delete_job_delivery_dlq(self, dlq_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/api/core/jobs/dlq/{dlq_id}")

    # ===== Gateway Admin (pairings/tokens) =====

    async def list_gateway_pairings(self, *, channel: Optional[str] = None, user_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if channel:
            params["channel"] = channel
        if user_id:
            params["user_id"] = user_id
        return await self._request("GET", "/api/core/gateway/pairings", params=params)

    async def upsert_gateway_pairing(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/gateway/pairings", json=data)

    async def delete_gateway_pairing(self, *, channel: str, channel_user_id: str) -> Dict[str, Any]:
        params: Dict[str, Any] = {"channel": channel, "channel_user_id": channel_user_id}
        return await self._request("DELETE", "/api/core/gateway/pairings", params=params)

    async def list_gateway_tokens(self, *, enabled: Optional[bool] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if enabled is not None:
            params["enabled"] = bool(enabled)
        return await self._request("GET", "/api/core/gateway/tokens", params=params)

    async def create_gateway_token(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/gateway/tokens", json=data)

    async def delete_gateway_token(self, token_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/api/core/gateway/tokens/{token_id}")

    # ===== Learning / Release Management (Phase 6) =====

    async def list_learning_artifacts(
        self,
        *,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if target_type:
            params["target_type"] = target_type
        if target_id:
            params["target_id"] = target_id
        if kind:
            params["kind"] = kind
        if status:
            params["status"] = status
        if trace_id:
            params["trace_id"] = trace_id
        if run_id:
            params["run_id"] = run_id
        return await self._request("GET", "/api/core/learning/artifacts", params=params)

    async def get_learning_artifact(self, artifact_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/learning/artifacts/{artifact_id}")

    async def set_learning_artifact_status(self, artifact_id: str, *, status: str, metadata_update: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/core/learning/artifacts/{artifact_id}/status",
            json={"status": status, "metadata_update": metadata_update or {}},
        )

    async def publish_release_candidate(self, candidate_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/learning/releases/{candidate_id}/publish", json=payload)

    async def rollback_release_candidate(self, candidate_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/learning/releases/{candidate_id}/rollback", json=payload)

    async def expire_releases(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/learning/releases/expire", json=payload)

    async def auto_rollback_regression(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/learning/auto-rollback/regression", json=payload)

    async def cleanup_rollback_approvals(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/learning/approvals/cleanup-rollback-approvals", json=payload)

    async def autocapture_to_prompt_revision(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/learning/autocapture/to_prompt_revision", json=payload)

    # ===== Approvals (reuse core approvals API) =====

    async def list_pending_approvals(
        self,
        *,
        user_id: Optional[str] = None,
        order_by: str = "priority_score",
        order_dir: str = "desc",
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"order_by": order_by, "order_dir": order_dir, "limit": limit, "offset": offset}
        if user_id:
            params["user_id"] = user_id
        return await self._request("GET", "/api/core/approvals/pending", params=params)

    async def get_approval_request(self, request_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/approvals/{request_id}")

    async def approve_request(self, request_id: str, approved_by: str, comments: str = "") -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/approvals/{request_id}/approve", json={"approved_by": approved_by, "comments": comments})

    async def reject_request(self, request_id: str, rejected_by: str, comments: str = "") -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/approvals/{request_id}/reject", json={"rejected_by": rejected_by, "comments": comments})

    # ===== Graph runs / checkpoints (ExecutionStore) =====

    async def list_graph_runs(
        self,
        limit: int = 100,
        offset: int = 0,
        graph_name: Optional[str] = None,
        status: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if graph_name:
            params["graph_name"] = graph_name
        if status:
            params["status"] = status
        if trace_id:
            params["trace_id"] = trace_id
        return await self._request("GET", "/api/core/graphs/runs", params=params)

    async def get_graph_run(self, run_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/graphs/runs/{run_id}")

    async def list_graph_checkpoints(self, run_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        return await self._request("GET", f"/api/core/graphs/runs/{run_id}/checkpoints", params=params)

    async def get_graph_checkpoint(self, run_id: str, checkpoint_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/graphs/runs/{run_id}/checkpoints/{checkpoint_id}")

    async def resume_graph_run(self, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new run from checkpoint (restore/resume)."""
        return await self._request("POST", f"/api/core/graphs/runs/{run_id}/resume", json=payload)

    async def resume_and_execute_graph_run(self, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Resume from checkpoint and continue executing (closes the loop)."""
        return await self._request("POST", f"/api/core/graphs/runs/{run_id}/resume/execute", json=payload)
    
    # ===== Agent Management =====
    
    async def list_agents(self, agent_type: Optional[str] = None, 
                          status: Optional[str] = None,
                          limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List all agents."""
        params = {"limit": limit, "offset": offset}
        if agent_type:
            params["agent_type"] = agent_type
        if status:
            params["status"] = status
        return await self._request("GET", "/api/core/agents", params=params)
    
    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get agent details."""
        return await self._request("GET", f"/api/core/agents/{agent_id}")
    
    async def create_agent(self, agent: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new agent."""
        return await self._request("POST", "/api/core/agents", json=agent)
    
    async def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update agent."""
        return await self._request("PUT", f"/api/core/agents/{agent_id}", json=updates)
    
    async def delete_agent(self, agent_id: str) -> Dict[str, Any]:
        """Delete agent."""
        return await self._request("DELETE", f"/api/core/agents/{agent_id}")
    
    async def start_agent(self, agent_id: str) -> Dict[str, Any]:
        """Start agent."""
        return await self._request("POST", f"/api/core/agents/{agent_id}/start")
    
    async def stop_agent(self, agent_id: str) -> Dict[str, Any]:
        """Stop agent."""
        return await self._request("POST", f"/api/core/agents/{agent_id}/stop")
    
    async def get_agent_skills(self, agent_id: str) -> Dict[str, Any]:
        """Get skills bound to agent."""
        return await self._request("GET", f"/api/core/agents/{agent_id}/skills")
    
    async def bind_agent_skills(self, agent_id: str, skill_ids: List[str]) -> Dict[str, Any]:
        """Bind skills to agent."""
        return await self._request("POST", f"/api/core/agents/{agent_id}/skills", json={"skill_ids": skill_ids})
    
    async def unbind_agent_skill(self, agent_id: str, skill_id: str) -> Dict[str, Any]:
        """Unbind skill from agent."""
        return await self._request("DELETE", f"/api/core/agents/{agent_id}/skills/{skill_id}")
    
    async def get_agent_tools(self, agent_id: str) -> Dict[str, Any]:
        """Get tools bound to agent."""
        return await self._request("GET", f"/api/core/agents/{agent_id}/tools")
    
    async def bind_agent_tools(self, agent_id: str, tool_ids: List[str]) -> Dict[str, Any]:
        """Bind tools to agent."""
        return await self._request("POST", f"/api/core/agents/{agent_id}/tools", json={"tool_ids": tool_ids})
    
    async def unbind_agent_tool(self, agent_id: str, tool_id: str) -> Dict[str, Any]:
        """Unbind tool from agent."""
        return await self._request("DELETE", f"/api/core/agents/{agent_id}/tools/{tool_id}")
    
    async def get_agent_history(self, agent_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get agent execution history."""
        return await self._request("GET", f"/api/core/agents/{agent_id}/history", params={"limit": limit, "offset": offset})
    
    async def execute_agent(self, agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent with input."""
        return await self._request("POST", f"/api/core/agents/{agent_id}/execute", json=data)
    
    async def get_execution(self, execution_id: str) -> Dict[str, Any]:
        """Get execution details."""
        return await self._request("GET", f"/api/core/agents/executions/{execution_id}")
    
    # ===== Skill Management =====
    
    async def list_skills(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        enabled_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List all skills."""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        if enabled_only:
            params["enabled_only"] = "true"
        return await self._request("GET", "/api/core/skills", params=params)
    
    async def get_skill(self, skill_id: str) -> Dict[str, Any]:
        """Get skill details."""
        return await self._request("GET", f"/api/core/skills/{skill_id}")
    
    async def create_skill(self, skill: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new skill."""
        return await self._request("POST", "/api/core/skills", json=skill)
    
    async def update_skill(self, skill_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update skill."""
        return await self._request("PUT", f"/api/core/skills/{skill_id}", json=updates)
    
    async def delete_skill(self, skill_id: str, *, delete_files: bool = False) -> Dict[str, Any]:
        """Delete skill (default soft delete; delete_files=true for hard delete)."""
        params: Dict[str, Any] = {}
        if delete_files:
            params["delete_files"] = "true"
        return await self._request("DELETE", f"/api/core/skills/{skill_id}", params=params)

    async def restore_skill(self, skill_id: str) -> Dict[str, Any]:
        """Restore a deprecated skill."""
        return await self._request("POST", f"/api/core/skills/{skill_id}/restore")

    # ===== MCP Management =====

    async def list_mcp_servers(self) -> Dict[str, Any]:
        """List MCP servers (filesystem-backed)."""
        return await self._request("GET", "/api/core/mcp/servers")

    async def enable_mcp_server(self, server_name: str) -> Dict[str, Any]:
        """Enable MCP server."""
        return await self._request("POST", f"/api/core/mcp/servers/{server_name}/enable")

    async def disable_mcp_server(self, server_name: str) -> Dict[str, Any]:
        """Disable MCP server."""
        return await self._request("POST", f"/api/core/mcp/servers/{server_name}/disable")

    # ===== Workspace (user-facing) =====

    async def list_workspace_agents(self, agent_type: Optional[str] = None, status: Optional[str] = None, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": str(limit), "offset": str(offset)}
        if agent_type:
            params["type"] = agent_type
        if status:
            params["status"] = status
        return await self._request("GET", "/api/core/workspace/agents", params=params)

    async def create_workspace_agent(self, agent: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/workspace/agents", json=agent)

    async def get_workspace_agent(self, agent_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/agents/{agent_id}")

    async def update_workspace_agent(self, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("PUT", f"/api/core/workspace/agents/{agent_id}", json=payload)

    async def delete_workspace_agent(self, agent_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/api/core/workspace/agents/{agent_id}")

    async def execute_workspace_agent(self, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/agents/{agent_id}/execute", json=payload)

    async def get_workspace_agent_skills(self, agent_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/agents/{agent_id}/skills")

    async def bind_workspace_agent_skills(self, agent_id: str, skill_ids: List[str]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/agents/{agent_id}/skills", json={"skill_ids": skill_ids})

    async def unbind_workspace_agent_skill(self, agent_id: str, skill_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/api/core/workspace/agents/{agent_id}/skills/{skill_id}")

    async def get_workspace_agent_tools(self, agent_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/agents/{agent_id}/tools")

    async def bind_workspace_agent_tools(self, agent_id: str, tool_ids: List[str]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/agents/{agent_id}/tools", json={"tool_ids": tool_ids})

    async def unbind_workspace_agent_tool(self, agent_id: str, tool_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/api/core/workspace/agents/{agent_id}/tools/{tool_id}")

    async def get_workspace_agent_history(self, agent_id: str, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/agents/{agent_id}/history", params={"limit": limit, "offset": offset})

    async def get_workspace_agent_versions(self, agent_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/agents/{agent_id}/versions")

    async def create_workspace_agent_version(self, agent_id: str, changes: str = "") -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/agents/{agent_id}/versions", json={"changes": changes})

    async def rollback_workspace_agent_version(self, agent_id: str, version: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/agents/{agent_id}/versions/{version}/rollback")

    async def list_workspace_skills(self, category: Optional[str] = None, status: Optional[str] = None, *, enabled_only: bool = False, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": str(limit), "offset": str(offset)}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        if enabled_only:
            params["enabled_only"] = "true"
        return await self._request("GET", "/api/core/workspace/skills", params=params)

    async def create_workspace_skill(self, skill: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/core/workspace/skills", json=skill)

    async def get_workspace_skill(self, skill_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/skills/{skill_id}")

    async def update_workspace_skill(self, skill_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("PUT", f"/api/core/workspace/skills/{skill_id}", json=payload)

    async def execute_workspace_skill(self, skill_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/skills/{skill_id}/execute", json=payload)

    async def list_workspace_skill_executions(self, skill_id: str, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/skills/{skill_id}/executions", params={"limit": limit, "offset": offset})

    async def get_workspace_skill_versions(self, skill_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/skills/{skill_id}/versions")

    async def get_workspace_skill_active_version(self, skill_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/core/workspace/skills/{skill_id}/active-version")

    async def rollback_workspace_skill_version(self, skill_id: str, version: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/skills/{skill_id}/versions/{version}/rollback")

    async def enable_workspace_skill(self, skill_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/skills/{skill_id}/enable")

    async def disable_workspace_skill(self, skill_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/skills/{skill_id}/disable")

    async def restore_workspace_skill(self, skill_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/skills/{skill_id}/restore")

    async def delete_workspace_skill(self, skill_id: str, *, delete_files: bool = False) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if delete_files:
            params["delete_files"] = "true"
        return await self._request("DELETE", f"/api/core/workspace/skills/{skill_id}", params=params)

    async def list_workspace_mcp_servers(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/core/workspace/mcp/servers")

    async def enable_workspace_mcp_server(self, server_name: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/mcp/servers/{server_name}/enable")

    async def disable_workspace_mcp_server(self, server_name: str) -> Dict[str, Any]:
        return await self._request("POST", f"/api/core/workspace/mcp/servers/{server_name}/disable")
    
    async def enable_skill(self, skill_id: str) -> Dict[str, Any]:
        """Enable skill."""
        return await self._request("POST", f"/api/core/skills/{skill_id}/enable")
    
    async def disable_skill(self, skill_id: str) -> Dict[str, Any]:
        """Disable skill."""
        return await self._request("POST", f"/api/core/skills/{skill_id}/disable")
    
    async def get_skill_agents(self, skill_id: str) -> Dict[str, Any]:
        """Get agents bound to skill."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/agents")
    
    async def get_skill_binding_stats(self, skill_id: str) -> Dict[str, Any]:
        """Get skill binding statistics."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/binding-stats")
    
    async def get_skill_versions(self, skill_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get skill version list."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/versions", params={"limit": limit, "offset": offset})
    
    async def get_skill_version(self, skill_id: str, version: str) -> Dict[str, Any]:
        """Get specific skill version."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/versions/{version}")
    
    async def rollback_skill_version(self, skill_id: str, version: str) -> Dict[str, Any]:
        """Rollback skill to specific version."""
        return await self._request("POST", f"/api/core/skills/{skill_id}/versions/{version}/rollback")
    
    # ===== Skill trigger_conditions (新增) =====
    
    async def get_skill_trigger_conditions(self, skill_id: str) -> Dict[str, Any]:
        """Get skill trigger conditions (routing rules)."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/trigger-conditions")
    
    async def update_skill_trigger_conditions(self, skill_id: str, conditions: Dict[str, Any]) -> Dict[str, Any]:
        """Update skill trigger conditions."""
        return await self._request("PUT", f"/api/core/skills/{skill_id}/trigger-conditions", json=conditions)
    
    async def test_skill_trigger(self, skill_id: str, test_input: Dict[str, Any]) -> Dict[str, Any]:
        """Test if skill would be triggered by given input."""
        return await self._request("POST", f"/api/core/skills/{skill_id}/test-trigger", json=test_input)
    
    # ===== Skill Evolution (新增) =====
    
    async def get_skill_evolution_status(self, skill_id: str) -> Dict[str, Any]:
        """Get skill evolution status (CAPTURED/FIX/DERIVED)."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/evolution")
    
    async def trigger_skill_evolution(self, skill_id: str, trigger_type: str) -> Dict[str, Any]:
        """Manually trigger skill evolution."""
        return await self._request("POST", f"/api/core/skills/{skill_id}/evolution", json={"trigger_type": trigger_type})
    
    async def get_skill_lineage(self, skill_id: str) -> Dict[str, Any]:
        """Get skill lineage (evolution history)."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/lineage")
    
    async def get_skill_captures(self, skill_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get captured interactions for skill."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/captures", params={"limit": limit, "offset": offset})
    
    async def get_skill_fixes(self, skill_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get applied fixes for skill."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/fixes", params={"limit": limit, "offset": offset})
    
    async def get_skill_derived(self, skill_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get derived skills from parent skill."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/derived", params={"limit": limit, "offset": offset})
    
    async def execute_skill(self, skill_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute skill with input."""
        return await self._request("POST", f"/api/core/skills/{skill_id}/execute", json=data)
    
    async def get_skill_execution(self, execution_id: str) -> Dict[str, Any]:
        """Get skill execution result."""
        return await self._request("GET", f"/api/core/skills/executions/{execution_id}")
    
    async def list_skill_executions(self, skill_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get skill execution history."""
        return await self._request("GET", f"/api/core/skills/{skill_id}/executions", params={"limit": limit, "offset": offset})
    
    # ===== Memory Management =====
    
    async def list_sessions(self, status: Optional[str] = None,
                            agent_type: Optional[str] = None,
                            limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List all sessions."""
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if agent_type:
            params["agent_type"] = agent_type
        return await self._request("GET", "/api/core/memory/sessions", params=params)
    
    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session details."""
        return await self._request("GET", f"/api/core/memory/sessions/{session_id}")
    
    async def create_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new session."""
        return await self._request("POST", "/api/core/memory/sessions", json=session)
    
    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete session."""
        return await self._request("DELETE", f"/api/core/memory/sessions/{session_id}")
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return await self._request("GET", "/api/core/memory/stats")
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get session context and messages."""
        return await self._request("GET", f"/api/core/memory/sessions/{session_id}/context")
    
    async def add_session_message(self, session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """Add message to session."""
        return await self._request("POST", f"/api/core/memory/sessions/{session_id}/messages", json=message)
    
    async def search_memory(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Search memory with vector similarity."""
        return await self._request("POST", "/api/core/memory/search", json=query)
    
    async def cleanup_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Clean up expired memories."""
        return await self._request("POST", "/api/core/memory/cleanup", json=params)
    
    async def export_memory(self, format: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Export memory data."""
        params = {}
        if format:
            params["format"] = format
        if session_id:
            params["session_id"] = session_id
        return await self._request("GET", "/api/core/memory/export", params=params)
    
    async def import_memory(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Import memory data."""
        return await self._request("POST", "/api/core/memory/import", json=data)
    
    # ===== Knowledge Management =====
    
    async def list_collections(self, status: Optional[str] = None,
                               limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List all collections."""
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return await self._request("GET", "/api/core/knowledge/collections", params=params)
    
    async def get_collection(self, collection_id: str) -> Dict[str, Any]:
        """Get collection details."""
        return await self._request("GET", f"/api/core/knowledge/collections/{collection_id}")
    
    async def create_collection(self, collection: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new collection."""
        return await self._request("POST", "/api/core/knowledge/collections", json=collection)
    
    async def update_collection(self, collection_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update collection."""
        return await self._request("PUT", f"/api/core/knowledge/collections/{collection_id}", json=updates)
    
    async def delete_collection(self, collection_id: str) -> Dict[str, Any]:
        """Delete collection."""
        return await self._request("DELETE", f"/api/core/knowledge/collections/{collection_id}")
    
    async def reindex_collection(self, collection_id: str) -> Dict[str, Any]:
        """Rebuild collection index."""
        return await self._request("POST", f"/api/core/knowledge/collections/{collection_id}/reindex")
    
    async def upload_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Upload document to knowledge base."""
        return await self._request("POST", "/api/core/knowledge/documents", json=document)
    
    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get document status."""
        return await self._request("GET", f"/api/core/knowledge/documents/{document_id}")
    
    async def list_collection_documents(self, collection_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List documents in collection."""
        return await self._request("GET", f"/api/core/knowledge/collections/{collection_id}/documents", params={"limit": limit, "offset": offset})
    
    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        """Delete document from knowledge base."""
        return await self._request("DELETE", f"/api/core/knowledge/documents/{document_id}")
    
    async def search_knowledge(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Search/retrieve knowledge."""
        return await self._request("POST", "/api/core/knowledge/search", json=query)
    
    async def get_search_logs(self, collection_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get search logs for collection."""
        return await self._request("GET", f"/api/core/knowledge/collections/{collection_id}/search/logs", params={"limit": limit, "offset": offset})
    
    # ===== Adapter Management =====
    
    async def list_adapters(self, provider: Optional[str] = None,
                            status: Optional[str] = None,
                            limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List all adapters."""
        params = {"limit": limit, "offset": offset}
        if provider:
            params["provider"] = provider
        if status:
            params["status"] = status
        return await self._request("GET", "/api/core/adapters", params=params)
    
    async def get_adapter(self, adapter_id: str) -> Dict[str, Any]:
        """Get adapter details."""
        return await self._request("GET", f"/api/core/adapters/{adapter_id}")
    
    async def create_adapter(self, adapter: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new adapter."""
        return await self._request("POST", "/api/core/adapters", json=adapter)
    
    async def update_adapter(self, adapter_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update adapter."""
        return await self._request("PUT", f"/api/core/adapters/{adapter_id}", json=updates)
    
    async def delete_adapter(self, adapter_id: str) -> Dict[str, Any]:
        """Delete adapter."""
        return await self._request("DELETE", f"/api/core/adapters/{adapter_id}")
    
    async def test_adapter(self, adapter_id: str) -> Dict[str, Any]:
        """Test adapter connection."""
        return await self._request("POST", f"/api/core/adapters/{adapter_id}/test")
    
    async def enable_adapter(self, adapter_id: str) -> Dict[str, Any]:
        """Enable adapter."""
        return await self._request("POST", f"/api/core/adapters/{adapter_id}/enable")
    
    async def disable_adapter(self, adapter_id: str) -> Dict[str, Any]:
        """Disable adapter."""
        return await self._request("POST", f"/api/core/adapters/{adapter_id}/disable")
    
    async def get_adapter_models(self, adapter_id: str) -> Dict[str, Any]:
        """Get adapter model list."""
        return await self._request("GET", f"/api/core/adapters/{adapter_id}/models")
    
    async def add_adapter_model(self, adapter_id: str, model: Dict[str, Any]) -> Dict[str, Any]:
        """Add model configuration."""
        return await self._request("POST", f"/api/core/adapters/{adapter_id}/models", json=model)
    
    async def update_adapter_model(self, adapter_id: str, model_name: str, model: Dict[str, Any]) -> Dict[str, Any]:
        """Update model configuration."""
        return await self._request("PUT", f"/api/core/adapters/{adapter_id}/models/{model_name}", json=model)
    
    async def delete_adapter_model(self, adapter_id: str, model_name: str) -> Dict[str, Any]:
        """Delete model configuration."""
        return await self._request("DELETE", f"/api/core/adapters/{adapter_id}/models/{model_name}")
    
    async def get_adapter_stats(self, adapter_id: str) -> Dict[str, Any]:
        """Get adapter call statistics."""
        return await self._request("GET", f"/api/core/adapters/{adapter_id}/stats")
    
    async def get_adapter_calls(self, adapter_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get adapter call history."""
        return await self._request("GET", f"/api/core/adapters/{adapter_id}/calls", params={"limit": limit, "offset": offset})
    
    async def get_adapter_model_distribution(self, adapter_id: str) -> Dict[str, Any]:
        """Get model call distribution."""
        return await self._request("GET", f"/api/core/adapters/{adapter_id}/model-distribution")
    
    # ===== Harness Management =====
    
    async def get_harness_status(self) -> Dict[str, Any]:
        """Get harness status."""
        return await self._request("GET", "/api/core/harness/status")
    
    async def get_harness_config(self) -> Dict[str, Any]:
        """Get harness configuration."""
        return await self._request("GET", "/api/core/harness/config")
    
    async def update_harness_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update harness configuration."""
        return await self._request("PUT", "/api/core/harness/config", json=config)
    
    async def get_harness_metrics(self) -> Dict[str, Any]:
        """Get harness metrics."""
        return await self._request("GET", "/api/core/harness/metrics")
    
    async def get_harness_logs(self, limit: int = 100, offset: int = 0,
                               status: Optional[str] = None,
                               agent: Optional[str] = None) -> Dict[str, Any]:
        """Get execution logs."""
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if agent:
            params["agent"] = agent
        return await self._request("GET", "/api/core/harness/logs", params=params)
    
    async def get_hooks(self) -> Dict[str, Any]:
        """Get all hooks."""
        return await self._request("GET", "/api/core/harness/hooks")
    
    async def add_hook(self, hook: Dict[str, Any]) -> Dict[str, Any]:
        """Add a hook."""
        return await self._request("POST", "/api/core/harness/hooks", json=hook)
    
    async def delete_hook(self, hook_id: str) -> Dict[str, Any]:
        """Delete a hook."""
        return await self._request("DELETE", f"/api/core/harness/hooks/{hook_id}")
    
    async def update_hook(self, hook_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a hook."""
        return await self._request("PUT", f"/api/core/harness/hooks/{hook_id}", json=updates)
    
    async def get_execution_detail(self, execution_id: str) -> Dict[str, Any]:
        """Get execution details."""
        return await self._request("GET", f"/api/core/harness/executions/{execution_id}")
    
    async def list_coordinators(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List all coordinators."""
        return await self._request("GET", "/api/core/harness/coordinators", params={"limit": limit, "offset": offset})
    
    async def create_coordinator(self, coordinator: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new coordinator."""
        return await self._request("POST", "/api/core/harness/coordinators", json=coordinator)
    
    async def get_coordinator(self, coordinator_id: str) -> Dict[str, Any]:
        """Get coordinator details."""
        return await self._request("GET", f"/api/core/harness/coordinators/{coordinator_id}")
    
    async def update_coordinator(self, coordinator_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update coordinator."""
        return await self._request("PUT", f"/api/core/harness/coordinators/{coordinator_id}", json=updates)
    
    async def delete_coordinator(self, coordinator_id: str) -> Dict[str, Any]:
        """Delete coordinator."""
        return await self._request("DELETE", f"/api/core/harness/coordinators/{coordinator_id}")
    
    async def get_feedback_config(self) -> Dict[str, Any]:
        """Get feedback loop configuration."""
        return await self._request("GET", "/api/core/harness/feedback/config")
    
    async def update_feedback_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update feedback loop configuration."""
        return await self._request("PUT", "/api/core/harness/feedback/config", json=config)
