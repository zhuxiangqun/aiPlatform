"""
Core Layer API Client

HTTP client for calling aiPlat-core layer API.
"""

import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class CoreAPIClientConfig:
    """Configuration for Core API client."""
    base_url: str = "http://localhost:8002"
    timeout: float = 30.0
    transport: Optional[httpx.BaseTransport] = None


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
        
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

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
    
    async def list_skills(self, skill_type: Optional[str] = None,
                          status: Optional[str] = None,
                          limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List all skills."""
        params = {"limit": limit, "offset": offset}
        if skill_type:
            params["skill_type"] = skill_type
        if status:
            params["status"] = status
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
    
    async def delete_skill(self, skill_id: str) -> Dict[str, Any]:
        """Delete skill."""
        return await self._request("DELETE", f"/api/core/skills/{skill_id}")
    
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
