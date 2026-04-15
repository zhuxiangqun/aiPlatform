"""
Infrastructure Management API

This is the REST API entry point for aiPlat-infra layer.
Provides all infrastructure management endpoints.
"""

from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime

from ..manager import InfraManager
from ..node import NodeManager
from ..service import ServiceManager
from ..storage import StorageManager
from ..network import NetworkManager
from ..scheduler import SchedulerManager
from ..monitoring import MonitoringManager
from ..model import ModelManager


class StatusResponse(BaseModel):
    status: str
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class MetricsResponse(BaseModel):
    metrics: list
    count: int


class HealthResponse(BaseModel):
    status: str
    message: str
    details: Dict[str, Any]
    timestamp: str


class DiagnosisResponse(BaseModel):
    healthy: bool
    issues: list
    recommendations: list
    details: Optional[Dict[str, Any]] = None


class ConfigUpdateRequest(BaseModel):
    config: Dict[str, Any]


class NodeCreateRequest(BaseModel):
    name: str
    ip: str = "10.0.0.1"
    gpu_model: str = "A100"
    gpu_count: int = 0
    driver_version: str = "535.54.03"
    labels: Dict[str, str] = Field(default_factory=dict)


class ServiceDeployRequest(BaseModel):
    name: str
    namespace: str = "ai-prod"
    type: str = "LLM"
    image: str
    replicas: int = 1
    gpu_count: int = 0
    gpu_type: str = "A100"
    config: Dict[str, Any] = Field(default_factory=dict)


class QuotaCreateRequest(BaseModel):
    name: str
    gpu_quota: int
    team: str


_infra_manager: Optional[InfraManager] = None


def get_infra_manager() -> InfraManager:
    """Get or create the infra manager singleton."""
    global _infra_manager
    if _infra_manager is None:
        _infra_manager = InfraManager()
        _infra_manager.register("node", NodeManager())
        _infra_manager.register("service", ServiceManager())
        _infra_manager.register("storage", StorageManager())
        _infra_manager.register("network", NetworkManager())
        _infra_manager.register("scheduler", SchedulerManager())
        _infra_manager.register("monitoring", MonitoringManager())
        _infra_manager.register("model", ModelManager())
    return _infra_manager


def create_app() -> FastAPI:
    """Create FastAPI application for aiPlat-infra."""
    app = FastAPI(
        title="aiPlat-infra API",
        description="Infrastructure Layer API - Node, Service, Storage, Network, Scheduler, Monitoring, Model",
        version="0.1.0",
    )
    
    manager = get_infra_manager()
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize managers on startup."""
        model_mgr = manager.get("model")
        if model_mgr and hasattr(model_mgr, 'initialize'):
            await model_mgr.initialize()
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}
    
    @app.get("/")
    async def root():
        """Root endpoint - API info."""
        return {
            "name": "aiPlat-infra",
            "version": "0.1.0",
            "description": "Infrastructure Layer API",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/health",
            "endpoints": {
                "status": "/api/infra/status",
                "health": "/api/infra/health",
                "metrics": "/api/infra/metrics",
                "nodes": "/api/infra/nodes",
                "models": "/api/infra/models",
                "services": "/api/infra/services",
                "scheduler": "/api/infra/scheduler",
                "storage": "/api/infra/storage",
                "network": "/api/infra/network",
                "monitoring": "/api/infra/monitoring",
            }
        }
    
    @app.get("/api/infra/status")
    async def get_infra_status():
        """Get infrastructure status."""
        try:
            status = await manager.get_all_status()
            return {
                "status": "success",
                "data": {name: s.value for name, s in status.items()}
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/health")
    async def health_check_infra():
        """Health check infrastructure."""
        try:
            health = await manager.health_check_all()
            return {
                "status": "success",
                "data": {
                    name: {
                        "status": h.status.value,
                        "message": h.message,
                        "details": h.details,
                        "timestamp": h.timestamp.isoformat()
                    }
                    for name, h in health.items()
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/metrics")
    async def get_infra_metrics():
        """Get infrastructure metrics."""
        try:
            metrics = await manager.get_all_metrics()
            return {
                "status": "success",
                "data": {
                    name: [
                        {
                            "name": m.name,
                            "value": m.value,
                            "unit": m.unit,
                            "labels": m.labels
                        }
                        for m in module_metrics
                    ]
                    for name, module_metrics in metrics.items()
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/diagnose")
    async def diagnose_infra():
        """Diagnose infrastructure."""
        try:
            diagnosis = await manager.diagnose_all()
            return {
                "status": "success",
                "data": diagnosis
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/managers")
    async def list_managers():
        """List all registered managers."""
        return {
            "status": "success",
            "data": manager.list_managers()
        }
    
    @app.get("/api/infra/managers/{name}/status")
    async def get_manager_status(name: str):
        """Get specific manager status."""
        try:
            mgr = manager.get(name)
            if not mgr:
                raise HTTPException(status_code=404, detail=f"Manager {name} not found")
            
            status = await mgr.get_status()
            return {
                "status": "success",
                "data": {
                    "name": name,
                    "status": status.value
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/managers/{name}/health")
    async def health_check_manager(name: str):
        """Health check specific manager."""
        try:
            mgr = manager.get(name)
            if not mgr:
                raise HTTPException(status_code=404, detail=f"Manager {name} not found")
            
            health = await mgr.health_check()
            return {
                "status": "success",
                "data": {
                    "name": name,
                    "health": {
                        "status": health.status.value,
                        "message": health.message,
                        "details": health.details,
                        "timestamp": health.timestamp.isoformat()
                    }
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/managers/{name}/metrics")
    async def get_manager_metrics(name: str):
        """Get specific manager metrics."""
        try:
            mgr = manager.get(name)
            if not mgr:
                raise HTTPException(status_code=404, detail=f"Manager {name} not found")
            
            metrics = await mgr.get_metrics()
            return {
                "status": "success",
                "data": {
                    "name": name,
                    "metrics": [
                        {
                            "name": m.name,
                            "value": m.value,
                            "unit": m.unit,
                            "labels": m.labels
                        }
                        for m in metrics
                    ]
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/managers/{name}/config")
    async def get_manager_config(name: str):
        """Get specific manager configuration."""
        try:
            mgr = manager.get(name)
            if not mgr:
                raise HTTPException(status_code=404, detail=f"Manager {name} not found")
            
            config = await mgr.get_config()
            return {
                "status": "success",
                "data": {
                    "name": name,
                    "config": config
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.put("/api/infra/managers/{name}/config")
    async def update_manager_config(name: str, request: ConfigUpdateRequest):
        """Update specific manager configuration."""
        try:
            mgr = manager.get(name)
            if not mgr:
                raise HTTPException(status_code=404, detail=f"Manager {name} not found")
            
            await mgr.update_config(request.config)
            return {
                "status": "success",
                "message": f"Configuration updated for {name}"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Node Management =====
    
    @app.get("/api/infra/nodes")
    async def list_nodes():
        """List all nodes."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            nodes = await node_mgr.list_nodes()
            return {
                "nodes": [
                    {
                        "name": n.name,
                        "ip": n.ip,
                        "gpu_model": n.gpu_model,
                        "gpu_count": n.gpu_count,
                        "driver_version": n.driver_version,
                        "status": n.status,
                        "gpus": [
                            {
                                "gpu_id": g.gpu_id,
                                "model": g.model,
                                "utilization": g.utilization,
                                "memory_used": g.memory_used,
                                "memory_total": g.memory_total,
                                "temperature": g.temperature,
                                "power_usage": g.power_usage,
                                "status": g.status
                            }
                            for g in n.gpus
                        ],
                        "labels": n.labels
                    }
                    for n in nodes
                ],
                "total": len(nodes),
                "healthy": sum(1 for n in nodes if n.status == "Ready")
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/nodes/{node_name}")
    async def get_node(node_name: str):
        """Get node details."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            node = await node_mgr.get_node(node_name)
            if not node:
                raise HTTPException(status_code=404, detail=f"Node {node_name} not found")
            
            return {
                "name": node.name,
                "ip": node.ip,
                "gpu_model": node.gpu_model,
                "gpu_count": node.gpu_count,
                "driver_version": node.driver_version,
                "status": node.status,
                "gpus": [
                    {
                        "gpu_id": g.gpu_id,
                        "model": g.model,
                        "utilization": g.utilization,
                        "memory_used": g.memory_used,
                        "memory_total": g.memory_total,
                        "temperature": g.temperature,
                        "power_usage": g.power_usage,
                        "status": g.status
                    }
                    for g in node.gpus
                ],
                "labels": node.labels
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/nodes")
    async def add_node(request: NodeCreateRequest):
        """Add a new node."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            node = await node_mgr.add_node(request.dict())
            return {
                "name": node.name,
                "status": node.status
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/infra/nodes/{node_name}")
    async def remove_node(node_name: str):
        """Remove a node."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            await node_mgr.remove_node(node_name)
            return {"name": node_name, "status": "deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/nodes/{node_name}/drain")
    async def drain_node(node_name: str):
        """Drain a node."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            await node_mgr.drain_node(node_name)
            return {"name": node_name, "status": "draining"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/nodes/{node_name}/restart")
    async def restart_node(node_name: str):
        """Restart a node."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            await node_mgr.restart_node(node_name)
            return {"name": node_name, "status": "restarting"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Service Management =====
    
    @app.get("/api/infra/services")
    async def list_services(namespace: Optional[str] = None):
        """List all services."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            services = await service_mgr.list_services(namespace)
            return {
                "services": [
                    {
                        "id": f"{s.namespace}/{s.name}",
                        "name": s.name,
                        "namespace": s.namespace,
                        "type": s.type,
                        "image": s.image,
                        "imageTag": s.image.split(":")[-1] if ":" in s.image else "latest",
                        "replicas": s.replicas,
                        "readyReplicas": s.ready_replicas,
                        "gpuCount": s.gpu_count,
                        "gpuType": s.gpu_type,
                        "status": s.status,
                        "createdAt": s.created_at.isoformat() if s.created_at else None
                    }
                    for s in services
                ],
                "total": len(services)
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/services/{service_name}")
    async def get_service(service_name: str):
        """Get service details."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            service = await service_mgr.get_service(service_name)
            if not service:
                raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
            
            return {
                "name": service.name,
                "namespace": service.namespace,
                "type": service.type,
                "image": service.image,
                "replicas": service.replicas,
                "ready_replicas": service.ready_replicas,
                "gpu_count": service.gpu_count,
                "gpu_type": service.gpu_type,
                "status": service.status
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/services")
    async def deploy_service(request: ServiceDeployRequest):
        """Deploy a new service."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            service = await service_mgr.deploy_service(request.dict())
            return {
                "name": service.name,
                "status": service.status
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/infra/services/{service_name}")
    async def delete_service(service_name: str):
        """Delete a service."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            await service_mgr.delete_service(service_name)
            return {"name": service_name, "status": "deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/services/{service_name}/scale")
    async def scale_service(service_name: str, replicas: int = Query(..., ge=0)):
        """Scale a service."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            await service_mgr.scale_service(service_name, replicas)
            return {"name": service_name, "replicas": replicas}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/services/{service_name}/restart")
    async def restart_service(service_name: str):
        """Restart a service."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            await service_mgr.restart_service(service_name)
            return {"name": service_name, "status": "restarting"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Scheduler Management =====
    
    @app.get("/api/infra/scheduler/quotas")
    async def list_quotas():
        """List all resource quotas."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                return []
            
            quotas = await scheduler_mgr.list_quotas()
            return [
                {
                    "id": q.id,
                    "name": q.name,
                    "gpuQuota": q.gpu_quota,
                    "gpuUsed": q.gpu_used,
                    "team": q.team,
                    "status": q.status
                }
                for q in quotas
            ] if quotas else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/scheduler/policies")
    async def list_scheduler_policies():
        """List all scheduling policies."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                return []
            
            policies = await scheduler_mgr.list_policies()
            return policies if policies else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/scheduler/tasks")
    async def list_tasks(queue: Optional[str] = None):
        """List all tasks."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                return []
            
            tasks = await scheduler_mgr.list_tasks(queue)
            return [
                {
                    "id": t.id,
                    "name": t.name,
                    "gpu_count": t.gpu_count,
                    "gpu_type": t.gpu_type,
                    "queue": t.queue,
                    "priority": t.priority,
                    "status": t.status,
                    "position": t.position,
                    "submitter": t.submitter,
                    "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None
                }
                for t in tasks
            ] if tasks else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/scheduler/autoscaling")
    async def list_autoscaling_policies():
        """List all autoscaling policies."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                return []
            
            policies = await scheduler_mgr.list_autoscaling_policies()
            return [
                {
                    "id": p.id,
                    "service": p.service,
                    "type": p.type,
                    "min_replicas": p.min_replicas,
                    "max_replicas": p.max_replicas,
                    "current_replicas": p.current_replicas,
                    "status": p.status
                }
                for p in policies
            ] if policies else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Storage Management =====
    
    @app.get("/api/infra/storage/pvcs")
    async def list_pvcs():
        """List all PVCs."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                return []
            
            pvcs = await storage_mgr.list_pvcs()
            return pvcs if pvcs else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/storage/collections")
    async def list_vector_collections():
        """List all vector collections."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                return []
            
            collections = await storage_mgr.list_collections()
            return collections if collections else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Network Management =====
    
    @app.get("/api/infra/network/ingresses")
    async def list_ingresses():
        """List all ingresses."""
        try:
            network_mgr = manager.get("network")
            if not network_mgr:
                return []
            
            ingresses = await network_mgr.list_ingresses()
            return ingresses if ingresses else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/network/services")
    async def list_network_services():
        """List all network services."""
        try:
            network_mgr = manager.get("network")
            if not network_mgr:
                return []
            
            services = await network_mgr.list_services()
            return services if services else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/network/policies")
    async def list_network_policies():
        """List all network policies."""
        try:
            network_mgr = manager.get("network")
            if not network_mgr:
                return []
            
            policies = await network_mgr.list_policies()
            return policies if policies else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Monitoring Management =====
    
    @app.get("/api/infra/monitoring/metrics/cluster")
    async def get_cluster_metrics():
        """Get cluster metrics."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                return {}
            
            metrics = await monitoring_mgr.get_cluster_metrics()
            return metrics if metrics else {}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/monitoring/metrics/gpus")
    async def get_gpu_metrics():
        """Get GPU metrics."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                return []
            
            metrics = await monitoring_mgr.get_gpu_metrics()
            return metrics if metrics else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/monitoring/alerts/rules")
    async def list_alert_rules():
        """List all alert rules."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                return []
            
            rules = await monitoring_mgr.list_alert_rules()
            return rules if rules else []
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Model Management =====
    
    @app.get("/api/infra/models")
    async def list_models(
        source: Optional[str] = None,
        type: Optional[str] = None,
        enabled: Optional[bool] = None,
        status: Optional[str] = None
    ):
        """List all models."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            models = await model_mgr.list_models(source, type, enabled, status)
            return {
                "models": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "displayName": m.display_name,
                        "type": m.type.value,
                        "provider": m.provider,
                        "source": m.source.value,
                        "enabled": m.enabled,
                        "status": m.status.value,
                        "description": m.description,
                        "tags": m.tags,
                        "capabilities": m.capabilities,
                        "config": {
                            "temperature": m.config.temperature,
                            "maxTokens": m.config.max_tokens,
                            "topP": m.config.top_p,
                            "frequencyPenalty": m.config.frequency_penalty,
                            "presencePenalty": m.config.presence_penalty,
                            "stop": m.config.stop,
                            "baseUrl": m.config.base_url,
                            "apiKeyEnv": m.config.api_key_env,
                        },
                        "stats": {
                            "requestsTotal": m.stats.requests_total,
                            "requestsSuccess": m.stats.requests_success,
                            "requestsFailed": m.stats.requests_failed,
                            "tokensTotal": m.stats.tokens_total,
                            "avgLatencyMs": m.stats.avg_latency_ms,
                        } if m.stats else None,
                        "createdAt": m.created_at.isoformat() if m.created_at else None,
                        "updatedAt": m.updated_at.isoformat() if m.updated_at else None,
                    }
                    for m in models
                ],
                "total": len(models)
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/models/providers")
    async def get_providers():
        """Get supported providers."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            providers = await model_mgr.get_providers()
            return {"providers": providers}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/models/local")
    async def scan_local_models(endpoint: Optional[str] = None):
        """Scan local Ollama models."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            models = await model_mgr.scan_local_models(endpoint)
            return {
                "models": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "provider": m.provider,
                        "status": m.status.value
                    }
                    for m in models
                ],
                "total": len(models)
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/models/{model_id}")
    async def get_model(model_id: str):
        """Get model by ID."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            model = await model_mgr.get_model(model_id)
            if not model:
                raise HTTPException(status_code=404, detail="Model not found")
            
            return {
                "id": model.id,
                "name": model.name,
                "displayName": model.display_name,
                "type": model.type.value,
                "provider": model.provider,
                "source": model.source.value,
                "enabled": model.enabled,
                "status": model.status.value,
                "config": {
                    "temperature": model.config.temperature,
                    "maxTokens": model.config.max_tokens,
                    "topP": model.config.top_p,
                    "frequencyPenalty": model.config.frequency_penalty,
                    "presencePenalty": model.config.presence_penalty,
                    "stop": model.config.stop,
                    "baseUrl": model.config.base_url,
                    "apiKeyEnv": model.config.api_key_env,
                    "headers": model.config.headers,
                },
                "description": model.description,
                "tags": model.tags,
                "capabilities": model.capabilities,
                "stats": {
                    "requestsTotal": model.stats.requests_total,
                    "requestsSuccess": model.stats.requests_success,
                    "requestsFailed": model.stats.requests_failed,
                    "tokensTotal": model.stats.tokens_total,
                    "avgLatencyMs": model.stats.avg_latency_ms,
                } if model.stats else None,
                "createdAt": model.created_at.isoformat() if model.created_at else None,
                "updatedAt": model.updated_at.isoformat() if model.updated_at else None,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    class ModelCreateRequest(BaseModel):
        name: str
        displayName: Optional[str] = None
        type: str = "chat"
        provider: str
        description: Optional[str] = None
        tags: Optional[List[str]] = None
        capabilities: Optional[List[str]] = None
        config: Optional[Dict[str, Any]] = None
    
    @app.post("/api/infra/models")
    async def add_model(request: ModelCreateRequest):
        """Add a new model (external only)."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            from ..model import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig
            
            config_data = request.config or {}
            model = ModelInfo(
                name=request.name,
                display_name=request.displayName,
                type=ModelType(request.type),
                provider=request.provider,
                source=ModelSource.EXTERNAL,
                enabled=True,
                status=ModelStatus.NOT_CONFIGURED,
                config=ModelConfig(
                    temperature=config_data.get("temperature", 0.7),
                    max_tokens=config_data.get("maxTokens", config_data.get("max_tokens", 2048)),
                    top_p=config_data.get("topP", config_data.get("top_p", 1.0)),
                    frequency_penalty=config_data.get("frequencyPenalty", config_data.get("frequency_penalty", 0.0)),
                    presence_penalty=config_data.get("presencePenalty", config_data.get("presence_penalty", 0.0)),
                    stop=config_data.get("stop", []),
                    api_key_env=config_data.get("apiKeyEnv", config_data.get("api_key_env")),
                    base_url=config_data.get("baseUrl", config_data.get("base_url")),
                    headers=config_data.get("headers", {}),
                ),
                description=request.description or "",
                tags=request.tags or [],
                capabilities=request.capabilities or ["chat"],
            )
            
            created = await model_mgr.add_model(model)
            return {
                "id": created.id,
                "name": created.name,
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    class ModelUpdateRequest(BaseModel):
        displayName: Optional[str] = None
        enabled: Optional[bool] = None
        description: Optional[str] = None
        tags: Optional[List[str]] = None
        capabilities: Optional[List[str]] = None
        config: Optional[Dict[str, Any]] = None
    
    @app.put("/api/infra/models/{model_id}")
    async def update_model(model_id: str, request: ModelUpdateRequest):
        """Update model configuration."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            updates = {}
            if request.displayName is not None:
                updates["display_name"] = request.displayName
            if request.enabled is not None:
                updates["enabled"] = request.enabled
            if request.description is not None:
                updates["description"] = request.description
            if request.tags is not None:
                updates["tags"] = request.tags
            if request.capabilities is not None:
                updates["capabilities"] = request.capabilities
            if request.config is not None:
                updates["config"] = request.config
            
            updated = await model_mgr.update_model(model_id, updates)
            if not updated:
                raise HTTPException(status_code=404, detail="Model not found")
            
            return {"id": updated.id, "status": "updated"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/infra/models/{model_id}")
    async def delete_model(model_id: str):
        """Delete a model (external only)."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            success = await model_mgr.delete_model(model_id)
            if not success:
                raise HTTPException(status_code=404, detail="Model not found")
            
            return {"id": model_id, "status": "deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/models/{model_id}/enable")
    async def enable_model(model_id: str):
        """Enable a model."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            updated = await model_mgr.enable_model(model_id)
            if not updated:
                raise HTTPException(status_code=404, detail="Model not found")
            
            return {"id": updated.id, "enabled": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/models/{model_id}/disable")
    async def disable_model(model_id: str):
        """Disable a model."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            updated = await model_mgr.disable_model(model_id)
            if not updated:
                raise HTTPException(status_code=404, detail="Model not found")
            
            return {"id": updated.id, "enabled": False}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/models/{model_id}/test/connectivity")
    async def test_model_connectivity(model_id: str):
        """Test model connectivity."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            result = await model_mgr.test_connectivity(model_id)
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/models/{model_id}/test/response")
    async def test_model_response(model_id: str):
        """Test model response."""
        try:
            model_mgr = manager.get("model")
            if not model_mgr:
                raise HTTPException(status_code=404, detail="Model manager not found")
            
            result = await model_mgr.test_response(model_id)
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Driver Management =====
    
    class DriverUpgradeRequest(BaseModel):
        version: str
        nodes: Optional[List[str]] = None
    
    class DriverRollbackRequest(BaseModel):
        version: str
        nodes: Optional[List[str]] = None
    
    @app.get("/api/infra/drivers")
    async def list_drivers():
        """List all GPU drivers."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            drivers = await node_mgr.list_drivers()
            return {
                "drivers": drivers,
                "total": len(drivers)
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/drivers/{driver_name}")
    async def get_driver(driver_name: str):
        """Get driver details."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            driver = await node_mgr.get_driver(driver_name)
            if not driver:
                raise HTTPException(status_code=404, detail=f"Driver {driver_name} not found")
            
            return driver
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/drivers/upgrade")
    async def upgrade_driver(request: DriverUpgradeRequest):
        """Upgrade GPU driver on specified nodes."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            result = await node_mgr.upgrade_driver(request.version, request.nodes)
            return {
                "status": "success",
                "message": f"Driver upgrade to {request.version} initiated",
                "nodes": result
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/drivers/rollback")
    async def rollback_driver(request: DriverRollbackRequest):
        """Rollback GPU driver on specified nodes."""
        try:
            node_mgr = manager.get("node")
            if not node_mgr:
                raise HTTPException(status_code=404, detail="Node manager not found")
            
            result = await node_mgr.rollback_driver(request.version, request.nodes)
            return {
                "status": "success",
                "message": f"Driver rollback to {request.version} initiated",
                "nodes": result
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Service Logs & Events =====
    
    @app.get("/api/infra/services/{service_name}/logs")
    async def get_service_logs(
        service_name: str,
        lines: int = Query(100, ge=1, le=10000),
        follow: bool = False
    ):
        """Get service logs."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            logs = await service_mgr.get_logs(service_name, lines, follow)
            return {
                "service": service_name,
                "logs": logs,
                "lines": len(logs) if logs else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/services/{service_name}/events")
    async def get_service_events(service_name: str):
        """Get service events."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            events = await service_mgr.get_events(service_name)
            return {
                "service": service_name,
                "events": events,
                "total": len(events) if events else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Image Management =====
    
    class ImageBuildRequest(BaseModel):
        name: str
        tag: str = "latest"
        dockerfile: str = "Dockerfile"
        context: Optional[str] = None
        build_args: Optional[Dict[str, str]] = None
    
    @app.get("/api/infra/images")
    async def list_images(type: Optional[str] = None, search: Optional[str] = None):
        """List all images."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            images = await service_mgr.list_images(type, search)
            return {
                "images": images,
                "total": len(images) if images else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/images/{image_id}")
    async def get_image(image_id: str):
        """Get image details."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            image = await service_mgr.get_image(image_id)
            if not image:
                raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
            
            return image
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/images/build")
    async def build_image(request: ImageBuildRequest):
        """Build a new image."""
        try:
            service_mgr = manager.get("service")
            if not service_mgr:
                raise HTTPException(status_code=404, detail="Service manager not found")
            
            result = await service_mgr.build_image(
                request.name,
                request.tag,
                request.dockerfile,
                request.context,
                request.build_args
            )
            return {
                "status": "success",
                "message": f"Image build initiated for {request.name}:{request.tag}",
                "build_id": result.get("build_id")
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Audit Logs =====
    
    @app.get("/api/infra/audit/logs")
    async def get_audit_logs(
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        user: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = Query(100, ge=1, le=1000)
    ):
        """Get audit logs."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                raise HTTPException(status_code=404, detail="Monitoring manager not found")
            
            logs = await monitoring_mgr.get_audit_logs(
                start_time=start_time,
                end_time=end_time,
                user=user,
                action=action,
                resource=resource,
                limit=limit
            )
            return {
                "logs": logs,
                "total": len(logs) if logs else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Quota CRUD =====
    
    @app.post("/api/infra/scheduler/quotas")
    async def create_quota(request: QuotaCreateRequest):
        """Create a resource quota."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                raise HTTPException(status_code=404, detail="Scheduler manager not found")
            
            quota = await scheduler_mgr.create_quota(request.dict())
            return {
                "id": quota.id,
                "name": quota.name,
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.put("/api/infra/scheduler/quotas/{quota_id}")
    async def update_quota(quota_id: str, request: QuotaCreateRequest):
        """Update a resource quota."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                raise HTTPException(status_code=404, detail="Scheduler manager not found")
            
            quota = await scheduler_mgr.update_quota(quota_id, request.dict())
            if not quota:
                raise HTTPException(status_code=404, detail=f"Quota {quota_id} not found")
            
            return {
                "id": quota.id,
                "name": quota.name,
                "status": "updated"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/infra/scheduler/quotas/{quota_id}")
    async def delete_quota(quota_id: str):
        """Delete a resource quota."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                raise HTTPException(status_code=404, detail="Scheduler manager not found")
            
            success = await scheduler_mgr.delete_quota(quota_id)
            if not success:
                raise HTTPException(status_code=404, detail=f"Quota {quota_id} not found")
            
            return {"id": quota_id, "status": "deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Task Management =====
    
    class TaskCreateRequest(BaseModel):
        name: str
        gpu_count: int = 1
        gpu_type: str = "A100"
        queue: str = "default"
        priority: int = 50
        config: Optional[Dict[str, Any]] = None
    
    @app.post("/api/infra/scheduler/tasks")
    async def create_task(request: TaskCreateRequest):
        """Submit a new task."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                raise HTTPException(status_code=404, detail="Scheduler manager not found")
            
            task = await scheduler_mgr.create_task(request.dict())
            return {
                "id": task.id,
                "name": task.name,
                "status": "queued"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/infra/scheduler/tasks/{task_id}")
    async def cancel_task(task_id: str):
        """Cancel a task."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                raise HTTPException(status_code=404, detail="Scheduler manager not found")
            
            success = await scheduler_mgr.cancel_task(task_id)
            if not success:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            return {"id": task_id, "status": "cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Autoscaling Management =====
    
    class AutoscalingPolicyRequest(BaseModel):
        service: str
        min_replicas: int = 1
        max_replicas: int = 10
        metrics: List[Dict[str, Any]] = []
    
    @app.post("/api/infra/scheduler/autoscaling")
    async def create_autoscaling_policy(request: AutoscalingPolicyRequest):
        """Create an autoscaling policy."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                raise HTTPException(status_code=404, detail="Scheduler manager not found")
            
            policy = await scheduler_mgr.create_autoscaling_policy(request.dict())
            return {
                "id": policy.id,
                "service": policy.service,
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/scheduler/history")
    async def get_autoscaling_history(
        service: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ):
        """Get autoscaling history."""
        try:
            scheduler_mgr = manager.get("scheduler")
            if not scheduler_mgr:
                raise HTTPException(status_code=404, detail="Scheduler manager not found")
            
            history = await scheduler_mgr.get_autoscaling_history(service, start_time, end_time)
            return {
                "history": history,
                "total": len(history) if history else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Storage CRUD =====
    
    class PVCCreateRequest(BaseModel):
        name: str
        size: str = "100Gi"
        storage_class: str = "standard"
        access_mode: str = "ReadWriteOnce"
    
    class CollectionCreateRequest(BaseModel):
        name: str
        dimension: int = 1536
        index_type: str = "IVF_FLAT"
        metric_type: str = "L2"
    
    @app.post("/api/infra/storage/pvc")
    async def create_pvc(request: PVCCreateRequest):
        """Create a PVC."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                raise HTTPException(status_code=404, detail="Storage manager not found")
            
            pvc = await storage_mgr.create_pvc(request.dict())
            return {
                "name": pvc.get("name"),
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/storage/pvc/{pvc_name}/resize")
    async def resize_pvc(pvc_name: str, size: str = Query(...)):
        """Resize a PVC."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                raise HTTPException(status_code=404, detail="Storage manager not found")
            
            result = await storage_mgr.resize_pvc(pvc_name, size)
            return {
                "name": pvc_name,
                "size": size,
                "status": "resizing"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/storage/pvc/{pvc_name}/snapshot")
    async def create_pvc_snapshot(pvc_name: str):
        """Create a PVC snapshot."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                raise HTTPException(status_code=404, detail="Storage manager not found")
            
            snapshot = await storage_mgr.create_snapshot(pvc_name)
            return {
                "pvc": pvc_name,
                "snapshot": snapshot.get("name"),
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/storage/vector/status")
    async def get_vector_status():
        """Get vector database status."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                raise HTTPException(status_code=404, detail="Storage manager not found")
            
            status = await storage_mgr.get_vector_status()
            return status
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/storage/vector/collections")
    async def create_collection(request: CollectionCreateRequest):
        """Create a vector collection."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                raise HTTPException(status_code=404, detail="Storage manager not found")
            
            collection = await storage_mgr.create_collection(request.dict())
            return {
                "name": collection.get("name"),
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/infra/storage/vector/collections/{collection_name}")
    async def delete_collection(collection_name: str):
        """Delete a vector collection."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                raise HTTPException(status_code=404, detail="Storage manager not found")
            
            success = await storage_mgr.delete_collection(collection_name)
            if not success:
                raise HTTPException(status_code=404, detail=f"Collection {collection_name} not found")
            
            return {"name": collection_name, "status": "deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/storage/models")
    async def list_model_storage():
        """List model storage."""
        try:
            storage_mgr = manager.get("storage")
            if not storage_mgr:
                raise HTTPException(status_code=404, detail="Storage manager not found")
            
            models = await storage_mgr.list_model_storage()
            return {
                "models": models,
                "total": len(models) if models else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Network CRUD =====
    
    class ServiceCreateRequest(BaseModel):
        name: str
        namespace: str = "default"
        type: str = "ClusterIP"
        ports: List[Dict[str, Any]] = []
        selector: Dict[str, str] = {}
    
    class IngressCreateRequest(BaseModel):
        name: str
        namespace: str = "default"
        host: str
        path: str = "/"
        service_name: str
        service_port: int = 80
        tls: bool = False
    
    class NetworkPolicyCreateRequest(BaseModel):
        name: str
        namespace: str = "default"
        pod_selector: Dict[str, str] = {}
        ingress_rules: List[Dict[str, Any]] = []
        egress_rules: List[Dict[str, Any]] = []
    
    @app.post("/api/infra/network/services")
    async def create_network_service(request: ServiceCreateRequest):
        """Create a network service."""
        try:
            network_mgr = manager.get("network")
            if not network_mgr:
                raise HTTPException(status_code=404, detail="Network manager not found")
            
            service = await network_mgr.create_service(request.dict())
            return {
                "name": service.get("name"),
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/network/ingress")
    async def create_ingress(request: IngressCreateRequest):
        """Create an ingress."""
        try:
            network_mgr = manager.get("network")
            if not network_mgr:
                raise HTTPException(status_code=404, detail="Network manager not found")
            
            ingress = await network_mgr.create_ingress(request.dict())
            return {
                "name": ingress.get("name"),
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/network/policies")
    async def create_network_policy(request: NetworkPolicyCreateRequest):
        """Create a network policy."""
        try:
            network_mgr = manager.get("network")
            if not network_mgr:
                raise HTTPException(status_code=404, detail="Network manager not found")
            
            policy = await network_mgr.create_policy(request.dict())
            return {
                "name": policy.get("name"),
                "status": "created"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/infra/network/test-connectivity")
    async def test_network_connectivity(
        source: str = Query(...),
        target: str = Query(...),
        port: int = Query(...)
    ):
        """Test network connectivity."""
        try:
            network_mgr = manager.get("network")
            if not network_mgr:
                raise HTTPException(status_code=404, detail="Network manager not found")
            
            result = await network_mgr.test_connectivity(source, target, port)
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== Monitoring Extended =====
    
    @app.get("/api/infra/monitoring/overview")
    async def get_monitoring_overview():
        """Get monitoring overview."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                raise HTTPException(status_code=404, detail="Monitoring manager not found")
            
            overview = await monitoring_mgr.get_overview()
            return overview
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/monitoring/nodes/{node_name}/metrics")
    async def get_node_metrics(node_name: str):
        """Get node metrics."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                raise HTTPException(status_code=404, detail="Monitoring manager not found")
            
            metrics = await monitoring_mgr.get_node_metrics(node_name)
            return metrics
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/monitoring/services/{service_name}/metrics")
    async def get_service_metrics(service_name: str):
        """Get service metrics."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                raise HTTPException(status_code=404, detail="Monitoring manager not found")
            
            metrics = await monitoring_mgr.get_service_metrics(service_name)
            return metrics
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/infra/monitoring/alerts/history")
    async def get_alert_history(
        service: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = Query(100, ge=1, le=1000)
    ):
        """Get alert history."""
        try:
            monitoring_mgr = manager.get("monitoring")
            if not monitoring_mgr:
                raise HTTPException(status_code=404, detail="Monitoring manager not found")
            
            history = await monitoring_mgr.get_alert_history(service, start_time, end_time, limit)
            return {
                "history": history,
                "total": len(history) if history else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return app