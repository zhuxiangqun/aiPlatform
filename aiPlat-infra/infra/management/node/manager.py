"""
Node Manager

Manages GPU physical nodes or Kubernetes worker nodes.
In standalone mode, automatically detects local machine as a node.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from ..schemas import NodeInfo, GPUStatus
from datetime import datetime
import time
import platform
import socket


def get_local_node_info() -> NodeInfo:
    """Get local machine information as a node."""
    import psutil
    
    hostname = socket.gethostname()
    system = platform.system()
    
    # Get macOS version name (e.g., "macOS 26.3.1")
    os_name = system.lower()
    if system == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["sw_vers", "-productVersion"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                os_name = f"macOS {version}"
        except Exception:
            os_name = "macOS"
    
    gpu_model = "Unknown"
    gpu_count = 0
    driver_version = "N/A"
    gpus = []
    
    try:
        import subprocess
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            output = result.stdout
            if "Apple M" in output or "Apple Silicon" in output:
                gpu_model = "Apple Silicon (Unified Memory)"
                gpu_count = 1
                driver_version = "Apple Silicon (Built-in)"
            elif "NVIDIA" in output:
                lines = output.split("\n")
                for line in lines:
                    if "NVIDIA" in line:
                        gpu_model = line.split(":")[-1].strip()
                        gpu_count = 1
                        break
                try:
                    nvidia_result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if nvidia_result.returncode == 0:
                        driver_version = nvidia_result.stdout.strip()
                except Exception:
                    pass
    except Exception:
        pass
    
    try:
        import psutil
        mem = psutil.virtual_memory()
        memory_total = mem.total
        memory_used = mem.used
        
        gpus = [
            GPUStatus(
                gpu_id="gpu-0",
                model=gpu_model,
                utilization=0.0,
                memory_used=memory_used,
                memory_total=memory_total,
                temperature=0.0,
                power_usage=0.0,
                status="Ready"
            )
        ]
        
        if "Apple Silicon" in gpu_model or "Apple M" in gpu_model:
            gpus[0].memory_shared = True
    except Exception:
        memory_total = 0
        memory_used = 0
        gpus = []
    
    return NodeInfo(
        name=hostname,
        ip="127.0.0.1",
        gpu_model=gpu_model,
        gpu_count=gpu_count,
        driver_version=driver_version,
        status="Ready",
        gpus=gpus,
        labels={
            "kubernetes.io/hostname": hostname,
            "node-type": "standalone",
            "os": os_name
        },
        conditions=[],
        created_at=datetime.now()
    )


class NodeManager(ManagementBase):
    """
    Manager for GPU nodes and Kubernetes worker nodes.
    
    Provides node lifecycle management, GPU status monitoring, and driver management.
    
    In standalone mode, automatically detects and adds the local machine as a node.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._nodes: Dict[str, NodeInfo] = {}
        self._driver_versions: List[str] = []
        self._node_count = 0
        self._gpu_count = 0
        self._healthy_nodes = 0
        
        standalone_mode = config.get("standalone_mode", True) if config else True
        
        if standalone_mode:
            local_node = get_local_node_info()
            self._nodes[local_node.name] = local_node
            self._node_count = 1
            self._gpu_count = local_node.gpu_count
            self._healthy_nodes = 1
    
    async def get_status(self) -> Status:
        """Get node module status."""
        try:
            if not self._nodes:
                return Status.UNKNOWN
            
            unhealthy_count = sum(
                1 for node in self._nodes.values()
                if node.status in ["NotReady", "Unknown"]
            )
            
            total_count = len(self._nodes)
            
            if unhealthy_count == 0:
                return Status.HEALTHY
            elif unhealthy_count < total_count:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get node metrics."""
        metrics = []
        timestamp = time.time()
        
        metrics.append(Metrics(
            name="node.count_total",
            value=len(self._nodes),
            unit="count",
            timestamp=timestamp,
            labels={"module": "node"}
        ))
        
        metrics.append(Metrics(
            name="node.gpu_count",
            value=self._gpu_count,
            unit="count",
            timestamp=timestamp,
            labels={"module": "node"}
        ))
        
        metrics.append(Metrics(
            name="node.healthy_count",
            value=self._healthy_nodes,
            unit="count",
            timestamp=timestamp,
            labels={"module": "node"}
        ))
        
        for node_name, node in self._nodes.items():
            metrics.append(Metrics(
                name="node.gpu_utilization",
                value=sum(g.utilization for g in node.gpus) / len(node.gpus) if node.gpus else 0,
                unit="ratio",
                timestamp=timestamp,
                labels={"node": node_name, "module": "node"}
            ))
            
            metrics.append(Metrics(
                name="node.gpu_temperature_avg",
                value=sum(g.temperature for g in node.gpus) / len(node.gpus) if node.gpus else 0,
                unit="celsius",
                timestamp=timestamp,
                labels={"node": node_name, "module": "node"}
            ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform node health check."""
        try:
            status = await self.get_status()
            
            issues = []
            details = {
                "total_nodes": len(self._nodes),
                "healthy_nodes": sum(1 for n in self._nodes.values() if n.status == "Ready"),
                "gpu_count": self._gpu_count
            }
            
            for node_name, node in self._nodes.items():
                if node.status != "Ready":
                    issues.append(f"Node {node_name} is {node.status}")
                
                for gpu in node.gpus:
                    if gpu.temperature > 85:
                        issues.append(f"GPU {gpu.gpu_id} on {node_name} has high temperature: {gpu.temperature}°C")
            
            if status == Status.HEALTHY:
                return HealthStatus(
                    status=status,
                    message="All nodes are healthy",
                    details=details
                )
            elif status == Status.DEGRADED:
                return HealthStatus(
                    status=status,
                    message=f"{len(issues)} node issues detected",
                    details={**details, "issues": issues}
                )
            else:
                return HealthStatus(
                    status=status,
                    message="Critical node failures detected",
                    details={**details, "issues": issues}
                )
        
        except Exception as e:
            return HealthStatus(
                status=Status.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "kubernetes_api": self._get_config_value("kubernetes_api", ""),
            "driver_versions": self._driver_versions,
            "auto_drain_before_upgrade": self._get_config_value("auto_drain_before_upgrade", False)
        }
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update node manager configuration."""
        if "kubernetes_api" in config:
            self.config["kubernetes_api"] = config["kubernetes_api"]
        if "driver_versions" in config:
            self._driver_versions = config["driver_versions"]
        if "auto_drain_before_upgrade" in config:
            self.config["auto_drain_before_upgrade"] = config["auto_drain_before_upgrade"]
    
    async def diagnose(self) -> DiagnosisResult:
        """Run diagnostic checks for nodes."""
        issues = []
        recommendations = []
        details = {}
        
        try:
            status = await self.get_status()
            details["status"] = status.value
            
            if status == Status.UNHEALTHY:
                issues.append("Node module is unhealthy")
                recommendations.append("Check Kubernetes API connection")
                recommendations.append("Verify node status with kubectl get nodes")
            
            health = await self.health_check()
            details["health"] = health.message
            
            if health.status == Status.DEGRADED:
                issues.append(f"Node health degraded: {health.message}")
                recommendations.append("Check node conditions and GPU status")
            
            metrics = await self.get_metrics()
            details["metrics_count"] = len(metrics)
            
            for metric in metrics:
                if metric.name == "node.gpu_temperature_avg" and metric.value > 80:
                    issues.append(f"High GPU temperature detected: {metric.labels.get('node')}")
                    recommendations.append("Check cooling system and reduce workload")
            
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
                recommendations=["Check node configuration and connectivity"],
                details={"error": str(e)}
            )
    
    async def list_nodes(self) -> List[NodeInfo]:
        """
        List all nodes.
        
        Returns:
            List[NodeInfo]: List of node information
        """
        return list(self._nodes.values())
    
    async def get_node(self, node_name: str) -> Optional[NodeInfo]:
        """
        Get node by name.
        
        Args:
            node_name: Node name
            
        Returns:
            NodeInfo or None if not found
        """
        return self._nodes.get(node_name)
    
    async def add_node(self, config: Dict[str, Any]) -> NodeInfo:
        """
        Add a new node.
        
        Args:
            config: Node configuration
            
        Returns:
            NodeInfo: Created node information
        """
        node_name = config.get("name", f"node-{len(self._nodes) + 1}")
        
        node = NodeInfo(
            name=node_name,
            ip=config.get("ip", "10.0.0.1"),
            gpu_model=config.get("gpu_model", "Unknown"),
            gpu_count=config.get("gpu_count", 0),
            driver_version=config.get("driver_version", "N/A"),
            status="Ready",
            gpus=[],
            labels=config.get("labels", {}),
            conditions=[],
            created_at=datetime.now()
        )
        
        self._nodes[node.name] = node
        self._node_count = len(self._nodes)
        self._gpu_count += node.gpu_count
        self._healthy_nodes = sum(1 for n in self._nodes.values() if n.status == "Ready")
        
        return node
    
    async def remove_node(self, node_name: str) -> None:
        """
        Remove a node.
        
        Args:
            node_name: Node name
        """
        if node_name in self._nodes:
            node = self._nodes[node_name]
            self._gpu_count -= node.gpu_count
            del self._nodes[node_name]
            self._node_count = len(self._nodes)
            self._healthy_nodes = sum(1 for n in self._nodes.values() if n.status == "Ready")
    
    async def drain_node(self, node_name: str) -> None:
        """
        Drain a node (mark as unschedulable and evict pods).
        
        Args:
            node_name: Node name
        """
        if node_name in self._nodes:
            self._nodes[node_name].status = "Draining"
    
    async def restart_node(self, node_name: str) -> None:
        """
        Restart a node.
        
        Args:
            node_name: Node name
        """
        if node_name in self._nodes:
            self._nodes[node_name].status = "Restarting"
    
    async def get_gpu_status(self, node_name: str) -> List[GPUStatus]:
        """
        Get GPU status for a node.
        
        Args:
            node_name: Node name
            
        Returns:
            List[GPUStatus]: List of GPU status
        """
        node = self._nodes.get(node_name)
        if node:
            return node.gpus
        return []
    
    async def get_driver_version(self, node_name: str) -> str:
        """
        Get GPU driver version for a node.
        
        Args:
            node_name: Node name
            
        Returns:
            str: Driver version
        """
        node = self._nodes.get(node_name)
        if node:
            return node.driver_version
        return "N/A"
    
    async def upgrade_driver(self, node_name: str, version: str) -> None:
        """
        Upgrade GPU driver on a node.
        
        Args:
            node_name: Node name
            version: Driver version
        """
        if node_name in self._nodes:
            self._nodes[node_name].driver_version = version
    
    async def list_drivers(self) -> List[Dict[str, Any]]:
        """List all GPU drivers across nodes."""
        drivers = {}
        for node in self._nodes.values():
            if node.driver_version not in drivers:
                drivers[node.driver_version] = {
                    "version": node.driver_version,
                    "nodes": [],
                    "gpu_models": set()
                }
            drivers[node.driver_version]["nodes"].append(node.name)
            drivers[node.driver_version]["gpu_models"].add(node.gpu_model)
        
        return [
            {
                "version": v["version"],
                "node_count": len(v["nodes"]),
                "nodes": v["nodes"],
                "gpu_models": list(v["gpu_models"])
            }
            for v in drivers.values()
        ]
    
    async def get_driver(self, version: str) -> Optional[Dict[str, Any]]:
        """Get driver details by version."""
        nodes_with_version = [
            node for node in self._nodes.values()
            if node.driver_version == version
        ]
        
        if not nodes_with_version:
            return None
        
        return {
            "version": version,
            "node_count": len(nodes_with_version),
            "nodes": [
                {
                    "name": node.name,
                    "gpu_model": node.gpu_model,
                    "gpu_count": node.gpu_count,
                    "status": node.status
                }
                for node in nodes_with_version
            ]
        }
    
    async def upgrade_driver_batch(self, version: str, nodes: Optional[List[str]] = None) -> List[str]:
        """Upgrade GPU driver on specified nodes (or all nodes if not specified)."""
        target_nodes = nodes if nodes else list(self._nodes.keys())
        upgraded = []
        
        for node_name in target_nodes:
            if node_name in self._nodes:
                self._nodes[node_name].driver_version = version
                upgraded.append(node_name)
        
        return upgraded
    
    async def rollback_driver(self, version: str, nodes: Optional[List[str]] = None) -> List[str]:
        """Rollback GPU driver to a previous version."""
        target_nodes = nodes if nodes else list(self._nodes.keys())
        rolled_back = []
        
        for node_name in target_nodes:
            if node_name in self._nodes:
                self._nodes[node_name].driver_version = version
                rolled_back.append(node_name)
        
        return rolled_back