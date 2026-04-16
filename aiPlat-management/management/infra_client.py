"""
Infrastructure API Client

HTTP client for calling aiPlat-infra layer API.
"""

import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from typing import Optional as _Optional


@dataclass
class InfraAPIClientConfig:
    """Configuration for Infra API client."""
    base_url: str = "http://localhost:8001"
    timeout: float = 30.0
    transport: _Optional[httpx.BaseTransport] = None


class InfraAPIClient:
    """HTTP client for aiPlat-infra API."""
    
    def __init__(self, config: Optional[InfraAPIClientConfig] = None):
        self.config = config or InfraAPIClientConfig()
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
        """Make HTTP request to infra API."""
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                transport=self.config.transport,
            )
        
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()
    
    # ===== Status & Health =====
    
    async def get_status(self) -> Dict[str, Any]:
        """Get infrastructure status."""
        return await self._request("GET", "/api/infra/status")
    
    async def get_health(self) -> Dict[str, Any]:
        """Get infrastructure health."""
        return await self._request("GET", "/api/infra/health")
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get infrastructure metrics."""
        return await self._request("GET", "/api/infra/metrics")
    
    async def diagnose(self) -> Dict[str, Any]:
        """Diagnose infrastructure."""
        return await self._request("GET", "/api/infra/diagnose")

    # ===== Managers (config/status/metrics) =====

    async def list_managers(self) -> Dict[str, Any]:
        """List all registered managers (infra internal modules)."""
        return await self._request("GET", "/api/infra/managers")

    async def get_manager_config(self, name: str) -> Dict[str, Any]:
        """Get specific manager configuration."""
        return await self._request("GET", f"/api/infra/managers/{name}/config")

    async def update_manager_config(self, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update specific manager configuration."""
        return await self._request("PUT", f"/api/infra/managers/{name}/config", json={"config": config})
    
    # ===== Node Management =====
    
    async def list_nodes(self) -> Dict[str, Any]:
        """List all nodes."""
        return await self._request("GET", "/api/infra/nodes")
    
    async def get_node(self, node_name: str) -> Dict[str, Any]:
        """Get node details."""
        return await self._request("GET", f"/api/infra/nodes/{node_name}")
    
    async def add_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new node."""
        return await self._request("POST", "/api/infra/nodes", json=node)
    
    async def remove_node(self, node_name: str) -> Dict[str, Any]:
        """Remove a node."""
        return await self._request("DELETE", f"/api/infra/nodes/{node_name}")
    
    async def drain_node(self, node_name: str) -> Dict[str, Any]:
        """Drain a node."""
        return await self._request("POST", f"/api/infra/nodes/{node_name}/drain")
    
    async def restart_node(self, node_name: str) -> Dict[str, Any]:
        """Restart a node."""
        return await self._request("POST", f"/api/infra/nodes/{node_name}/restart")
    
    # ===== Service Management =====
    
    async def list_services(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """List all services."""
        params = {}
        if namespace:
            params["namespace"] = namespace
        return await self._request("GET", "/api/infra/services", params=params)
    
    async def get_service(self, service_name: str) -> Dict[str, Any]:
        """Get service details."""
        return await self._request("GET", f"/api/infra/services/{service_name}")
    
    async def deploy_service(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy a new service."""
        return await self._request("POST", "/api/infra/services", json=service)
    
    async def delete_service(self, service_name: str) -> Dict[str, Any]:
        """Delete a service."""
        return await self._request("DELETE", f"/api/infra/services/{service_name}")
    
    async def scale_service(self, service_name: str, replicas: int) -> Dict[str, Any]:
        """Scale a service."""
        return await self._request("POST", f"/api/infra/services/{service_name}/scale?replicas={replicas}")
    
    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        """Restart a service."""
        return await self._request("POST", f"/api/infra/services/{service_name}/restart")
    
    # ===== Scheduler Management =====
    
    async def list_quotas(self) -> List[Dict[str, Any]]:
        """List all resource quotas."""
        result = await self._request("GET", "/api/infra/scheduler/quotas")
        return result if isinstance(result, list) else []
    
    async def list_scheduler_policies(self) -> List[Dict[str, Any]]:
        """List all scheduling policies."""
        result = await self._request("GET", "/api/infra/scheduler/policies")
        return result if isinstance(result, list) else []
    
    async def list_tasks(self, queue: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all tasks."""
        params = {}
        if queue:
            params["queue"] = queue
        result = await self._request("GET", "/api/infra/scheduler/tasks", params=params)
        return result if isinstance(result, list) else []
    
    async def list_autoscaling_policies(self) -> List[Dict[str, Any]]:
        """List all autoscaling policies."""
        result = await self._request("GET", "/api/infra/scheduler/autoscaling")
        return result if isinstance(result, list) else []
    
    # ===== Storage Management =====
    
    async def list_pvcs(self) -> List[Dict[str, Any]]:
        """List all PVCs."""
        result = await self._request("GET", "/api/infra/storage/pvcs")
        return result if isinstance(result, list) else []
    
    async def list_vector_collections(self) -> List[Dict[str, Any]]:
        """List all vector collections."""
        result = await self._request("GET", "/api/infra/storage/collections")
        return result if isinstance(result, list) else []
    
    # ===== Network Management =====
    
    async def list_ingresses(self) -> List[Dict[str, Any]]:
        """List all ingresses."""
        result = await self._request("GET", "/api/infra/network/ingresses")
        return result if isinstance(result, list) else []
    
    async def list_network_services(self) -> List[Dict[str, Any]]:
        """List all network services."""
        result = await self._request("GET", "/api/infra/network/services")
        return result if isinstance(result, list) else []
    
    async def list_network_policies(self) -> List[Dict[str, Any]]:
        """List all network policies."""
        result = await self._request("GET", "/api/infra/network/policies")
        return result if isinstance(result, list) else []
    
    # ===== Monitoring Management =====
    
    async def get_cluster_metrics(self) -> Dict[str, Any]:
        """Get cluster metrics."""
        result = await self._request("GET", "/api/infra/monitoring/metrics/cluster")
        return result if isinstance(result, dict) else {}
    
    async def get_gpu_metrics(self) -> List[Dict[str, Any]]:
        """Get GPU metrics."""
        result = await self._request("GET", "/api/infra/monitoring/metrics/gpus")
        return result if isinstance(result, list) else []
    
    async def list_alert_rules(self) -> List[Dict[str, Any]]:
        """List all alert rules."""
        result = await self._request("GET", "/api/infra/monitoring/alerts/rules")
        return result if isinstance(result, list) else []
    
    # ===== Model Management =====
    
    async def list_models(self, source: Optional[str] = None, type: Optional[str] = None,
                          enabled: Optional[bool] = None, status: Optional[str] = None) -> Dict[str, Any]:
        """List all models."""
        params = {}
        if source:
            params["source"] = source
        if type:
            params["type"] = type
        if enabled is not None:
            params["enabled"] = str(enabled).lower()
        if status:
            params["status"] = status
        return await self._request("GET", "/api/infra/models", params=params)
    
    async def get_model(self, model_id: str) -> Dict[str, Any]:
        """Get model details."""
        return await self._request("GET", f"/api/infra/models/{model_id}")
    
    async def add_model(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new model."""
        return await self._request("POST", "/api/infra/models", json=model)
    
    async def update_model(self, model_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update model configuration."""
        return await self._request("PUT", f"/api/infra/models/{model_id}", json=updates)
    
    async def delete_model(self, model_id: str) -> Dict[str, Any]:
        """Delete a model."""
        return await self._request("DELETE", f"/api/infra/models/{model_id}")
    
    async def enable_model(self, model_id: str) -> Dict[str, Any]:
        """Enable a model."""
        return await self._request("POST", f"/api/infra/models/{model_id}/enable")
    
    async def disable_model(self, model_id: str) -> Dict[str, Any]:
        """Disable a model."""
        return await self._request("POST", f"/api/infra/models/{model_id}/disable")
    
    async def test_model_connectivity(self, model_id: str) -> Dict[str, Any]:
        """Test model connectivity."""
        return await self._request("POST", f"/api/infra/models/{model_id}/test/connectivity")
    
    async def test_model_response(self, model_id: str) -> Dict[str, Any]:
        """Test model response."""
        return await self._request("POST", f"/api/infra/models/{model_id}/test/response")
    
    async def scan_local_models(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Scan local Ollama models."""
        params = {}
        if endpoint:
            params["endpoint"] = endpoint
        return await self._request("GET", "/api/infra/models/local", params=params)
    
    async def get_model_providers(self) -> Dict[str, Any]:
        """Get supported providers."""
        return await self._request("GET", "/api/infra/models/providers")
