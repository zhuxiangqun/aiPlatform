"""
Service Manager

Manages AI inference services. In standalone mode, monitors real processes.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from ..schemas import ServiceInfo, ImageInfo
from datetime import datetime
import time


def get_real_processes() -> List[Dict[str, Any]]:
    """Get real running processes for standalone mode."""
    processes = []
    
    try:
        import psutil
        
        target_processes = [
            {"name": "aiPlat-infra", "cmdline": "infra.management.api.run_server", "port": 8001, "type": "Infrastructure"},
            {"name": "aiPlat-management", "cmdline": "uvicorn management.server", "port": 8000, "type": "Management"},
            {"name": "frontend", "cmdline": "vite", "port": 5173, "type": "Frontend"},
            {"name": "python", "cmdline": "python", "port": None, "type": "Python"},
            {"name": "node", "cmdline": "node", "port": None, "type": "Node.js"},
        ]
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'cpu_percent']):
            try:
                proc_info = proc.info
                cmdline = ' '.join(proc_info.get('cmdline', []) or [])
                proc_name = proc_info.get('name', '').lower()
                
                for target in target_processes:
                    if target['cmdline'].lower() in cmdline.lower():
                        memory_mb = proc_info.get('memory_info').rss / 1024 / 1024 if proc_info.get('memory_info') else 0
                        cpu_percent = proc_info.get('cpu_percent', 0) or 0
                        
                        processes.append({
                            "name": target['name'],
                            "pid": proc_info['pid'],
                            "type": target['type'],
                            "port": target['port'],
                            "memory_mb": round(memory_mb, 1),
                            "cpu_percent": round(cpu_percent, 1),
                            "status": "Running",
                            "cmdline": cmdline[:100]
                        })
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        pass
    
    return processes


class ServiceManager(ManagementBase):
    """
    Manager for AI inference services.
    
    In standalone mode, monitors real processes.
    In cluster mode, manages Kubernetes services.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._services: Dict[str, ServiceInfo] = {}
        self._images: Dict[str, ImageInfo] = {}
        self._service_count = 0
        self._running_count = 0
        self._standalone_mode = config.get("standalone_mode", True) if config else True
    
    def _refresh_services_from_processes(self):
        """Refresh services list from real processes."""
        if not self._standalone_mode:
            return
        
        processes = get_real_processes()
        self._services.clear()
        
        for proc in processes:
            service = ServiceInfo(
                name=proc['name'],
                namespace="standalone",
                type=proc['type'],
                image="local",
                replicas=1,
                ready_replicas=1 if proc['status'] == 'Running' else 0,
                gpu_count=0,
                gpu_type="CPU",
                status=proc['status'],
                pods=[{
                    "name": f"{proc['name']}-{proc['pid']}",
                    "status": proc['status'],
                    "restarts": 0,
                    "age": "0d"
                }],
                config={
                    "port": proc.get('port'),
                    "pid": proc['pid'],
                    "memory_mb": proc['memory_mb'],
                    "cpu_percent": proc['cpu_percent']
                },
                created_at=datetime.now()
            )
            self._services[f"standalone/{proc['name']}"] = service
        
        self._service_count = len(self._services)
        self._running_count = sum(1 for s in self._services.values() if s.status == 'Running')
    
    async def get_status(self) -> Status:
        """Get service module status."""
        try:
            if self._standalone_mode:
                self._refresh_services_from_processes()
            
            if not self._services:
                return Status.UNKNOWN
            
            unhealthy_count = sum(
                1 for service in self._services.values()
                if service.status in ["Failed", "Unknown"]
            )
            
            total_count = len(self._services)
            
            if unhealthy_count == 0:
                return Status.HEALTHY
            elif unhealthy_count < total_count:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get service metrics."""
        if self._standalone_mode:
            self._refresh_services_from_processes()
        
        metrics = []
        timestamp = time.time()
        
        metrics.append(Metrics(
            name="service.count_total",
            value=len(self._services),
            unit="count",
            timestamp=timestamp,
            labels={"module": "service"}
        ))
        
        metrics.append(Metrics(
            name="service.running_count",
            value=self._running_count,
            unit="count",
            timestamp=timestamp,
            labels={"module": "service"}
        ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform service health check."""
        if self._standalone_mode:
            self._refresh_services_from_processes()
        
        issues = []
        details = {
            "total_services": len(self._services),
            "running_services": self._running_count
        }
        
        for service_name, service in self._services.items():
            if service.status == "Failed":
                issues.append(f"Service {service_name} is failed")
            elif service.status == "Pending":
                issues.append(f"Service {service_name} is pending")
        
        status = await self.get_status()
        
        if status == Status.HEALTHY:
            return HealthStatus(
                status=status,
                message="All services are healthy",
                details=details
            )
        elif status == Status.DEGRADED:
            return HealthStatus(
                status=status,
                message=f"{len(issues)} service issues detected",
                details={**details, "issues": issues}
            )
        else:
            return HealthStatus(
                status=status,
                message="Critical service failures detected",
                details={**details, "issues": issues}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
    
    async def diagnose(self) -> DiagnosisResult:
        """Run diagnostic checks for services."""
        if self._standalone_mode:
            self._refresh_services_from_processes()
        
        issues = []
        recommendations = []
        details = {}
        
        try:
            status = await self.get_status()
            details["status"] = status.value
            
            if status == Status.UNHEALTHY:
                issues.append("Service module is unhealthy")
                recommendations.append("Check process status")
                recommendations.append("Review service logs")
            
            metrics = await self.get_metrics()
            details["metrics_count"] = len(metrics)
            
            healthy = len(issues) == 0
            
            return DiagnosisResult(
                healthy=healthy,
                issues=issues,
                recommendations=recommendations,
                details=details
            )
        
        except Exception as e:
            return DiagnosisResult(
                healthy=False,
                issues=[f"Diagnosis failed: {str(e)}"],
                recommendations=["Check service configuration"],
                details={"error": str(e)}
            )
    
    async def list_services(self, namespace: Optional[str] = None) -> List[ServiceInfo]:
        """
        List all services.
        
        Args:
            namespace: Optional namespace filter
            
        Returns:
            List[ServiceInfo]: List of service information
        """
        if self._standalone_mode:
            self._refresh_services_from_processes()
        
        services = list(self._services.values())
        
        if namespace:
            services = [s for s in services if s.namespace == namespace]
        
        return services
    
    async def get_service(self, service_name: str) -> Optional[ServiceInfo]:
        """
        Get service by name.
        
        Args:
            service_name: Service name
            
        Returns:
            ServiceInfo or None if not found
        """
        if self._standalone_mode:
            self._refresh_services_from_processes()
        
        for key, service in self._services.items():
            if key.endswith(f"/{service_name}") or key == service_name:
                return service
        return None
    
    async def deploy_service(self, config: Dict[str, Any]) -> ServiceInfo:
        """Deploy a new service (not supported in standalone mode)."""
        if self._standalone_mode:
            raise RuntimeError("Deploy not supported in standalone mode")
        
        service = ServiceInfo(
            name=config.get("name", f"service-{len(self._services) + 1}"),
            namespace=config.get("namespace", "default"),
            type=config.get("type", "Unknown"),
            image=config.get("image", ""),
            replicas=config.get("replicas", 1),
            ready_replicas=0,
            gpu_count=config.get("gpu_count", 0),
            gpu_type=config.get("gpu_type", "Unknown"),
            status="Pending",
            pods=[],
            config=config,
            created_at=datetime.now()
        )
        
        key = f"{service.namespace}/{service.name}"
        self._services[key] = service
        self._service_count = len(self._services)
        
        return service
    
    async def delete_service(self, service_name: str) -> None:
        """Delete a service (not supported in standalone mode)."""
        if self._standalone_mode:
            raise RuntimeError("Delete not supported in standalone mode")
        
        keys_to_delete = [k for k in self._services if k.endswith(f"/{service_name}")]
        for key in keys_to_delete:
            del self._services[key]
        self._service_count = len(self._services)
    
    async def scale_service(self, service_name: str, replicas: int) -> None:
        """Scale a service (not supported in standalone mode)."""
        if self._standalone_mode:
            raise RuntimeError("Scale not supported in standalone mode")
        
        for key, service in self._services.items():
            if key.endswith(f"/{service_name}"):
                service.replicas = replicas
    
    async def restart_service(self, service_name: str) -> None:
        """Restart a service (not supported in standalone mode)."""
        if self._standalone_mode:
            raise RuntimeError("Restart not supported in standalone mode")
        
        for key, service in self._services.items():
            if key.endswith(f"/{service_name}"):
                service.status = "Restarting"
    
    async def get_service_logs(self, service_name: str, lines: int = 100) -> str:
        """Get service logs (not supported in standalone mode)."""
        if self._standalone_mode:
            return "Logs not available in standalone mode"
        return ""
    
    async def get_logs(self, service_name: str, lines: int = 100, follow: bool = False) -> List[str]:
        """Get service logs."""
        if self._standalone_mode:
            return ["Logs not available in standalone mode"]
        return []
    
    async def get_events(self, service_name: str) -> List[Dict[str, Any]]:
        """Get service events."""
        if self._standalone_mode:
            return []
        return []
    
    async def list_images(self, type: Optional[str] = None, search: Optional[str] = None) -> List[ImageInfo]:
        """List available images."""
        images = list(self._images.values())
        if type:
            images = [i for i in images if i.type == type]
        if search:
            images = [i for i in images if search.lower() in i.name.lower()]
        return images
    
    async def get_image(self, image_id: str) -> Optional[Dict[str, Any]]:
        """Get image details."""
        image = self._images.get(image_id)
        if not image:
            return None
        return {
            "id": image.id,
            "name": image.name,
            "tag": image.tag,
            "type": image.type,
            "size": image.size,
            "created_at": image.created_at.isoformat() if image.created_at else None
        }
    
    async def get_image_details(self, image_id: str) -> Optional[ImageInfo]:
        """Get image details."""
        return self._images.get(image_id)
    
    async def build_image(
        self,
        name: str,
        tag: str = "latest",
        dockerfile: str = "Dockerfile",
        context: Optional[str] = None,
        build_args: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Build a new image."""
        import uuid
        build_id = str(uuid.uuid4())[:8]
        
        return {
            "build_id": build_id,
            "name": name,
            "tag": tag,
            "status": "building",
            "message": "Image build initiated (not supported in standalone mode)"
        }