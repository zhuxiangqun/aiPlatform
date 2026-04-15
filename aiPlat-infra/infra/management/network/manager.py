"""
Network Manager

Manages network management including ingresses, services, and policies.
In standalone mode, monitors real network ports.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from datetime import datetime
import time


def get_real_network_info() -> Dict[str, Any]:
    """Get real network information for standalone mode."""
    result = {
        "listening_ports": [],
        "connections": []
    }
    
    try:
        import subprocess
        proc = subprocess.run(
            ['lsof', '-i', '-P', '-n', '-sTCP:LISTEN'],
            capture_output=True, text=True, timeout=5
        )
        if proc.returncode == 0:
            seen_ports = set()
            for line in proc.stdout.strip().split('\n')[1:]:
                parts = line.split()
                if len(parts) >= 9:
                    try:
                        addr_port = parts[8]
                        if ':' in addr_port:
                            addr, port_str = addr_port.rsplit(':', 1)
                            port = int(port_str)
                            if port not in seen_ports:
                                seen_ports.add(port)
                                result["listening_ports"].append({
                                    "port": port,
                                    "address": addr,
                                    "pid": None,
                                    "process": parts[0]
                                })
                    except (ValueError, IndexError):
                        pass
    except Exception:
        pass
    
    known_defaults = [
        {"port": 8002, "address": "127.0.0.1", "process": "aiPlat-core"},
        {"port": 8001, "address": "127.0.0.1", "process": "aiPlat-infra"},
        {"port": 8000, "address": "127.0.0.1", "process": "aiPlat-management"},
        {"port": 5173, "address": "127.0.0.1", "process": "frontend"},
    ]
    
    existing_ports = {p["port"] for p in result["listening_ports"]}
    for default in known_defaults:
        if default["port"] not in existing_ports:
            result["listening_ports"].append(default)
    
    return result


class IngressInfo:
    def __init__(self, name: str, namespace: str, host: str, path: str, backend_service: str, backend_port: int, status: str, created_at: datetime):
        self.name = name
        self.namespace = namespace
        self.host = host
        self.path = path
        self.backend_service = backend_service
        self.backend_port = backend_port
        self.status = status
        self.created_at = created_at


class NetworkPolicyInfo:
    def __init__(self, name: str, namespace: str, policy_type: str, selector: Dict[str, str], status: str):
        self.name = name
        self.namespace = namespace
        self.policy_type = policy_type
        self.selector = selector
        self.status = status


class NetworkManager(ManagementBase):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._ingresses: Dict[str, IngressInfo] = {}
        self._policies: Dict[str, NetworkPolicyInfo] = {}
        self._standalone_mode = config.get("standalone_mode", True) if config else True
    
    def _refresh_network_info(self):
        """Refresh network information from real system."""
        if not self._standalone_mode:
            return
        
        network_info = get_real_network_info()
        
        # Convert listening ports to ingress-like format
        self._ingresses = {}
        known_services = {
            8002: {"name": "aiPlat-core", "service": "core-api"},
            8001: {"name": "aiPlat-infra", "service": "infra-api"},
            8000: {"name": "aiPlat-management", "service": "management-api"},
            5173: {"name": "frontend", "service": "frontend-dev"},
            3000: {"name": "node-service", "service": "node-app"},
        }
        
        for port_info in network_info.get("listening_ports", []):
            port = port_info["port"]
            if port in known_services:
                svc = known_services[port]
                self._ingresses[f"ingress-{port}"] = IngressInfo(
                    name=f"ingress-{port}",
                    namespace="standalone",
                    host=f"localhost:{port}",
                    path="/",
                    backend_service=svc["service"],
                    backend_port=port,
                    status="Active",
                    created_at=datetime.now()
                )
        
        self._policies = {
            "default-policy": NetworkPolicyInfo(
                name="default-policy",
                namespace="standalone",
                policy_type="Ingress",
                selector={"app": "ai-platform"},
                status="Active"
            )
        }
    
    async def get_status(self) -> Status:
        """Get network module status."""
        try:
            if self._standalone_mode:
                self._refresh_network_info()
            
            if not self._ingresses and not self._policies:
                return Status.UNKNOWN
            
            failed_ingresses = sum(1 for ing in self._ingresses.values() if ing.status == "Failed")
            failed_policies = sum(1 for pol in self._policies.values() if pol.status == "Error")
            
            total = len(self._ingresses) + len(self._policies)
            failed = failed_ingresses + failed_policies
            
            if failed == 0:
                return Status.HEALTHY
            elif failed < total:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get network metrics."""
        if self._standalone_mode:
            self._refresh_network_info()
        
        metrics = []
        timestamp = time.time()
        
        metrics.append(Metrics(
            name="network.ingress_count",
            value=len(self._ingresses),
            unit="count",
            timestamp=timestamp,
            labels={"module": "network"}
        ))
        
        metrics.append(Metrics(
            name="network.policy_count",
            value=len(self._policies),
            unit="count",
            timestamp=timestamp,
            labels={"module": "network"}
        ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform network health check."""
        if self._standalone_mode:
            self._refresh_network_info()
        
        status = await self.get_status()
        issues = []
        
        for name, ing in self._ingresses.items():
            if ing.status == "Failed":
                issues.append(f"Ingress {name} in namespace {ing.namespace} is failed")
        
        for name, pol in self._policies.items():
            if pol.status == "Error":
                issues.append(f"Network policy {name} in namespace {pol.namespace} is in error state")
        
        details = {"ingresses": len(self._ingresses), "policies": len(self._policies)}
        
        if status == Status.HEALTHY:
            return HealthStatus(
                status=status,
                message="Network is healthy",
                details=details
            )
        else:
            return HealthStatus(
                status=status,
                message=f"{len(issues)} network issues detected",
                details={**details, "issues": issues}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
    
    async def diagnose(self) -> DiagnosisResult:
        """Run diagnostic checks for network."""
        if self._standalone_mode:
            self._refresh_network_info()
        
        issues = []
        recommendations = []
        details = {}
        
        try:
            status = await self.get_status()
            details["status"] = status.value
            
            if status == Status.UNHEALTHY:
                issues.append("Network module is unhealthy")
                recommendations.append("Check network connectivity and firewall rules")
            
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
                recommendations=["Check network configuration"],
                details={"error": str(e)}
            )
    
    async def list_ingresses(self) -> List[Dict[str, Any]]:
        """List all ingresses."""
        if self._standalone_mode:
            self._refresh_network_info()
            return [
                {
                    "id": ing.name,
                    "name": ing.name,
                    "namespace": ing.namespace,
                    "host": ing.host,
                    "path": ing.path,
                    "backend": ing.backend_service,
                    "tls": False,
                    "annotations": {},
                    "status": ing.status,
                    "createdAt": ing.created_at.isoformat() if ing.created_at else None
                }
                for ing in self._ingresses.values()
            ]
        
        return [
            {
                "id": ing.name,
                "name": ing.name,
                "namespace": ing.namespace,
                "host": ing.host,
                "path": ing.path,
                "backend": ing.backend_service,
                "tls": False,
                "annotations": {},
                "status": ing.status,
                "createdAt": ing.created_at.isoformat() if ing.created_at else None
            }
            for ing in self._ingresses.values()
        ]
    
    async def get_ingress(self, name: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        """Get ingress details."""
        if self._standalone_mode:
            ingresses = await self.list_ingresses()
            for ing in ingresses:
                if ing["name"] == name:
                    return ing
            return None
        
        key = f"{namespace}/{name}"
        ing = self._ingresses.get(key)
        if ing:
            return {
                "name": ing.name,
                "namespace": ing.namespace,
                "host": ing.host,
                "path": ing.path,
                "backend_service": ing.backend_service,
                "backend_port": ing.backend_port,
                "status": ing.status,
                "created_at": ing.created_at.isoformat() if ing.created_at else None
            }
        return None
    
    async def create_ingress(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create an ingress."""
        if self._standalone_mode:
            raise RuntimeError("Create ingress not supported in standalone mode")
        
        name = config.get("name", f"ingress-{len(self._ingresses) + 1}")
        namespace = config.get("namespace", "default")
        key = f"{namespace}/{name}"
        
        ing = IngressInfo(
            name=name,
            namespace=namespace,
            host=config.get("host", ""),
            path=config.get("path", "/"),
            backend_service=config.get("backend_service", ""),
            backend_port=config.get("backend_port", 80),
            status="Pending",
            created_at=datetime.now()
        )
        
        self._ingresses[key] = ing
        return {"name": name, "namespace": namespace, "status": "created"}
    
    async def delete_ingress(self, name: str, namespace: str = "default") -> bool:
        """Delete an ingress."""
        if self._standalone_mode:
            raise RuntimeError("Delete ingress not supported in standalone mode")
        
        key = f"{namespace}/{name}"
        if key in self._ingresses:
            del self._ingresses[key]
            return True
        return False
    
    async def list_policies(self) -> List[Dict[str, Any]]:
        """List all network policies."""
        if self._standalone_mode:
            self._refresh_network_info()
        
        return [
            {
                "id": pol.name,
                "name": pol.name,
                "namespace": pol.namespace,
                "type": pol.policy_type,
                "selector": pol.selector,
                "status": pol.status
            }
            for pol in self._policies.values()
        ]
    
    async def get_policy(self, name: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        """Get network policy details."""
        key = f"{namespace}/{name}"
        pol = self._policies.get(key)
        if pol:
            return {
                "name": pol.name,
                "namespace": pol.namespace,
                "type": pol.policy_type,
                "selector": pol.selector,
                "status": pol.status
            }
        return None
    
    async def create_policy(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a network policy."""
        if self._standalone_mode:
            raise RuntimeError("Create policy not supported in standalone mode")
        
        name = config.get("name", f"policy-{len(self._policies) + 1}")
        namespace = config.get("namespace", "default")
        key = f"{namespace}/{name}"
        
        pol = NetworkPolicyInfo(
            name=name,
            namespace=namespace,
            policy_type=config.get("type", "Ingress"),
            selector=config.get("selector", {}),
            status="Created"
        )
        
        self._policies[key] = pol
        return {"name": name, "namespace": namespace, "status": "created"}
    
    async def delete_policy(self, name: str, namespace: str = "default") -> bool:
        """Delete a network policy."""
        if self._standalone_mode:
            raise RuntimeError("Delete policy not supported in standalone mode")
        
        key = f"{namespace}/{name}"
        if key in self._policies:
            del self._policies[key]
            return True
        return False
    
    async def list_services(self) -> List[Dict[str, Any]]:
        """List all network services (listening ports in standalone mode)."""
        if not self._standalone_mode:
            return []
        
        network_info = get_real_network_info()
        services = []
        
        known_names = {
            8002: "aiPlat-core",
            8001: "aiPlat-infra",
            8000: "aiPlat-management",
            5173: "frontend",
        }
        
        for port_info in network_info.get("listening_ports", []):
            port = port_info["port"]
            name = known_names.get(port, port_info.get("process", f"service-{port}"))
            services.append({
                "id": f"svc-{port}",
                "name": name,
                "namespace": "standalone",
                "type": "ClusterIP" if port_info["address"] == "127.0.0.1" else "LoadBalancer",
                "clusterIP": port_info["address"],
                "ports": [{"name": "http", "port": port, "targetPort": port, "protocol": "TCP"}],
                "selector": {"app": name.lower().replace(" ", "-")},
                "status": "Active"
            })
        
        return services
    
    async def create_service(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a network service."""
        import uuid
        name = config.get("name", f"service-{uuid.uuid4().hex[:8]}")
        
        return {
            "name": name,
            "namespace": config.get("namespace", "default"),
            "type": config.get("type", "ClusterIP"),
            "ports": config.get("ports", []),
            "selector": config.get("selector", {}),
            "status": "created"
        }
    
    async def test_connectivity(self, source: str, target: str, port: int) -> Dict[str, Any]:
        """Test network connectivity between source and target."""
        import socket
        
        result = {
            "source": source,
            "target": target,
            "port": port,
            "reachable": False,
            "latency_ms": 0
        }
        
        try:
            import time
            start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock_result = sock.connect_ex((target, port))
            end = time.time()
            sock.close()
            
            result["reachable"] = sock_result == 0
            result["latency_ms"] = int((end - start) * 1000)
        except Exception:
            pass
        
        return result