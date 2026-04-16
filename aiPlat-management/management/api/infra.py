"""
Infrastructure Management API Router

This router provides unified API endpoints for infrastructure management.
It calls aiPlat-infra layer's REST API (running on port 8001) for actual operations.

Architecture:
- aiPlat-management (this layer): Management system, unified API entry point
- aiPlat-infra (8001): Infrastructure business layer, actual implementation
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
import httpx

from ..infra_client import InfraAPIClient, InfraAPIClientConfig


router = APIRouter(prefix="/infra", tags=["infrastructure"])


def get_infra_client(request: Request) -> InfraAPIClient:
    """Get infra API client from app.state (single source of truth)."""
    client = getattr(request.app.state, "infra_client", None)
    if client is not None:
        return client
    # fallback (should not happen): build from config
    cfg = request.app.state.config.get("management", {}).get("layers", {}).get("infra", {}) if hasattr(request.app.state, "config") else {}
    base_url = cfg.get("endpoint", "http://localhost:8001")
    timeout = float(cfg.get("timeout", 30.0) or 30.0)
    client = InfraAPIClient(InfraAPIClientConfig(base_url=base_url, timeout=timeout))
    request.app.state.infra_client = client
    return client


# ===== Status & Health =====

@router.get("/status")
async def get_infra_status(request: Request):
    """Get infrastructure status."""
    try:
        client = get_infra_client(request)
        result = await client.get_status()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/health")
async def health_check_infra(request: Request):
    """Health check infrastructure."""
    try:
        client = get_infra_client(request)
        result = await client.get_health()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/metrics")
async def get_infra_metrics(request: Request):
    """Get infrastructure metrics."""
    try:
        client = get_infra_client(request)
        result = await client.get_metrics()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


# ===== Node Management =====

@router.get("/nodes")
async def list_nodes(request: Request):
    """List all nodes."""
    try:
        client = get_infra_client(request)
        result = await client.list_nodes()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/nodes/{node_name}")
async def get_node(node_name: str, request: Request):
    """Get node details."""
    try:
        client = get_infra_client(request)
        result = await client.get_node(node_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/nodes")
async def add_node(node: dict, request: Request):
    """Add a new node."""
    try:
        client = get_infra_client(request)
        result = await client.add_node(node)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.delete("/nodes/{node_name}")
async def remove_node(node_name: str, request: Request):
    """Remove a node."""
    try:
        client = get_infra_client(request)
        result = await client.remove_node(node_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/nodes/{node_name}/drain")
async def drain_node(node_name: str, request: Request):
    """Drain a node."""
    try:
        client = get_infra_client(request)
        result = await client.drain_node(node_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/nodes/{node_name}/restart")
async def restart_node(node_name: str, request: Request):
    """Restart a node."""
    try:
        client = get_infra_client(request)
        result = await client.restart_node(node_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


# ===== Service Management =====

@router.get("/services")
async def list_services(request: Request, namespace: Optional[str] = None):
    """List all services."""
    try:
        client = get_infra_client(request)
        result = await client.list_services(namespace)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/services/{service_name}")
async def get_service(service_name: str, request: Request):
    """Get service details."""
    try:
        client = get_infra_client(request)
        result = await client.get_service(service_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/services")
async def deploy_service(service: dict, request: Request):
    """Deploy a new service."""
    try:
        client = get_infra_client(request)
        result = await client.deploy_service(service)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.delete("/services/{service_name}")
async def delete_service(service_name: str, request: Request):
    """Delete a service."""
    try:
        client = get_infra_client(request)
        result = await client.delete_service(service_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/services/{service_name}/scale")
async def scale_service(service_name: str, replicas: int, request: Request):
    """Scale a service."""
    try:
        client = get_infra_client(request)
        result = await client.scale_service(service_name, replicas)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/services/{service_name}/restart")
async def restart_service(service_name: str, request: Request):
    """Restart a service."""
    try:
        client = get_infra_client(request)
        result = await client.restart_service(service_name)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


# ===== Scheduler Management =====

@router.get("/scheduler/quotas")
async def list_quotas(request: Request):
    """List all resource quotas."""
    try:
        client = get_infra_client(request)
        result = await client.list_quotas()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/scheduler/policies")
async def list_scheduler_policies(request: Request):
    """List all scheduling policies."""
    try:
        client = get_infra_client(request)
        result = await client.list_scheduler_policies()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/scheduler/tasks")
async def list_scheduler_tasks(request: Request):
    """List all tasks."""
    try:
        client = get_infra_client(request)
        result = await client.list_tasks()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/scheduler/autoscaling")
async def list_autoscaling_policies(request: Request):
    """List all autoscaling policies."""
    try:
        client = get_infra_client(request)
        result = await client.list_autoscaling_policies()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


# ===== Storage Management =====

@router.get("/storage/pvcs")
async def list_pvcs(request: Request):
    """List all PVCs."""
    try:
        client = get_infra_client(request)
        result = await client.list_pvcs()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/storage/collections")
async def list_vector_collections(request: Request):
    """List all vector collections."""
    try:
        client = get_infra_client(request)
        result = await client.list_vector_collections()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


# ===== Network Management =====

@router.get("/network/ingresses")
async def list_ingresses(request: Request):
    """List all ingresses."""
    try:
        client = get_infra_client(request)
        result = await client.list_ingresses()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/network/services")
async def list_network_services(request: Request):
    """List all network services."""
    try:
        client = get_infra_client(request)
        result = await client.list_network_services()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/network/policies")
async def list_network_policies(request: Request):
    """List all network policies."""
    try:
        client = get_infra_client(request)
        result = await client.list_network_policies()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


# ===== Monitoring Management =====

@router.get("/monitoring/metrics/cluster")
async def get_cluster_metrics(request: Request):
    """Get cluster metrics."""
    try:
        client = get_infra_client(request)
        result = await client.get_cluster_metrics()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/monitoring/metrics/gpus")
async def get_gpu_metrics(request: Request):
    """Get GPU metrics."""
    try:
        client = get_infra_client(request)
        result = await client.get_gpu_metrics()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/monitoring/alerts/rules")
async def list_alert_rules(request: Request):
    """List all alert rules."""
    try:
        client = get_infra_client(request)
        result = await client.list_alert_rules()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


# ===== Model Management =====

@router.get("/models")
async def list_models(
    request: Request,
    source: Optional[str] = None,
    type: Optional[str] = None,
    enabled: Optional[bool] = None,
    status: Optional[str] = None,
):
    """List all models."""
    try:
        client = get_infra_client(request)
        result = await client.list_models(source, type, enabled, status)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/models/providers")
async def get_model_providers(request: Request):
    """Get supported providers."""
    try:
        client = get_infra_client(request)
        result = await client.get_model_providers()
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/models/local")
async def scan_local_models(request: Request, endpoint: Optional[str] = None):
    """Scan local Ollama models."""
    try:
        client = get_infra_client(request)
        result = await client.scan_local_models(endpoint)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.get("/models/{model_id}")
async def get_model(model_id: str, request: Request):
    """Get model details."""
    try:
        client = get_infra_client(request)
        result = await client.get_model(model_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/models")
async def add_model(model: dict, request: Request):
    """Add a new model."""
    try:
        client = get_infra_client(request)
        result = await client.add_model(model)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.put("/models/{model_id}")
async def update_model(model_id: str, updates: dict, request: Request):
    """Update model configuration."""
    try:
        client = get_infra_client(request)
        result = await client.update_model(model_id, updates)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.delete("/models/{model_id}")
async def delete_model(model_id: str, request: Request):
    """Delete a model."""
    try:
        client = get_infra_client(request)
        result = await client.delete_model(model_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/models/{model_id}/enable")
async def enable_model(model_id: str, request: Request):
    """Enable a model."""
    try:
        client = get_infra_client(request)
        result = await client.enable_model(model_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/models/{model_id}/disable")
async def disable_model(model_id: str, request: Request):
    """Disable a model."""
    try:
        client = get_infra_client(request)
        result = await client.disable_model(model_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/models/{model_id}/test/connectivity")
async def test_model_connectivity(model_id: str, request: Request):
    """Test model connectivity."""
    try:
        client = get_infra_client(request)
        result = await client.test_model_connectivity(model_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")


@router.post("/models/{model_id}/test/response")
async def test_model_response(model_id: str, request: Request):
    """Test model response."""
    try:
        client = get_infra_client(request)
        result = await client.test_model_response(model_id)
        return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Infra API unavailable: {str(e)}")
