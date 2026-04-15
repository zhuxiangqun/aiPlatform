"""
Resources Manager

Manages compute resources including GPU, CPU, and memory.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics
from ..schemas import ResourceStats, NodeInfo, AllocatedResource
from datetime import datetime


class ResourcesManager(ManagementBase):
    """
    Manager for compute resources.
    
    Responsible for managing GPU nodes, CPU resources, and memory allocations.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._nodes: Dict[str, NodeInfo] = {}
        self._allocations: Dict[str, AllocatedResource] = {}
    
    async def get_status(self) -> Status:
        """Get resources module status."""
        try:
            # Check if any nodes are available
            if not self._nodes:
                return Status.UNKNOWN
            
            # Check node health
            healthy_count = sum(1 for node in self._nodes.values() if node.status == "healthy")
            total_count = len(self._nodes)
            
            if healthy_count == total_count:
                return Status.HEALTHY
            elif healthy_count > 0:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get resource metrics."""
        metrics = []
        timestamp = datetime.now().timestamp()
        
        # GPU utilization
        gpu_util = self._get_config_value("monitoring.gpu_utilization_threshold", 0.9)
        metrics.append(Metrics(
            name="resources.gpu_utilization",
            value=0.75,  # Placeholder
            unit="ratio",
            timestamp=timestamp,
            labels={"module": "resources"}
        ))
        
        # GPU memory
        metrics.append(Metrics(
            name="resources.gpu_memory_used",
            value=32768,  # Placeholder
            unit="MB",
            timestamp=timestamp,
            labels={"module": "resources"}
        ))
        
        # CPU usage
        metrics.append(Metrics(
            name="resources.cpu_usage",
            value=0.65,  # Placeholder
            unit="ratio",
            timestamp=timestamp,
            labels={"module": "resources"}
        ))
        
        # Memory usage
        metrics.append(Metrics(
            name="resources.memory_usage",
            value=0.70,  # Placeholder
            unit="ratio",
            timestamp=timestamp,
            labels={"module": "resources"}
        ))
        
        # Nodes count
        metrics.append(Metrics(
            name="resources.nodes_total",
            value=len(self._nodes),
            unit="count",
            timestamp=timestamp,
            labels={"module": "resources"}
        ))
        
        # Healthy nodes
        healthy_count = sum(1 for node in self._nodes.values() if node.status == "healthy")
        metrics.append(Metrics(
            name="resources.nodes_healthy",
            value=healthy_count,
            unit="count",
            timestamp=timestamp,
            labels={"module": "resources"}
        ))
        
        # Active allocations
        metrics.append(Metrics(
            name="resources.allocations_active",
            value=len(self._allocations),
            unit="count",
            timestamp=timestamp,
            labels={"module": "resources"}
        ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform resources health check."""
        try:
            status = await self.get_status()
            
            if status == Status.HEALTHY:
                return HealthStatus(
                    status=status,
                    message="All nodes are healthy",
                    details={"nodes": len(self._nodes)}
                )
            elif status == Status.DEGRADED:
                healthy_count = sum(1 for node in self._nodes.values() if node.status == "healthy")
                return HealthStatus(
                    status=status,
                    message=f"Some nodes are unhealthy: {healthy_count}/{len(self._nodes)} healthy",
                    details={"healthy_nodes": healthy_count, "total_nodes": len(self._nodes)}
                )
            else:
                return HealthStatus(
                    status=status,
                    message="All nodes are unhealthy",
                    details={"nodes": len(self._nodes)}
                )
        
        except Exception as e:
            return HealthStatus(
                status=Status.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
    
    # Resources specific methods
    
    async def list_nodes(self, filters: Dict[str, Any] = None) -> List[NodeInfo]:
        """
        List compute nodes.
        
        Args:
            filters: Optional filters
        
        Returns:
            List of node information
        """
        nodes = list(self._nodes.values())
        
        if filters:
            # Apply filters
            if "status" in filters:
                nodes = [n for n in nodes if n.status == filters["status"]]
            if "gpu_type" in filters:
                nodes = [n for n in nodes if n.gpu_type == filters["gpu_type"]]
        
        return nodes
    
    async def allocate(self, request: Dict[str, Any]) -> AllocatedResource:
        """
        Allocate resources.
        
        Args:
            request: Allocation request
        
        Returns:
            Allocated resource
        """
        allocation_id = f"alloc-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        allocation = AllocatedResource(
            allocation_id=allocation_id,
            resource_type=request.get("resource_type", "gpu"),
            amount=request.get("amount", 1),
            allocated_at=datetime.now(),
            expires_at=request.get("expires_at")
        )
        
        self._allocations[allocation_id] = allocation
        return allocation
    
    async def release(self, allocation_id: str) -> bool:
        """
        Release allocated resources.
        
        Args:
            allocation_id: Allocation ID
        
        Returns:
            True if released successfully
        """
        if allocation_id in self._allocations:
            del self._allocations[allocation_id]
            return True
        return False
    
    async def get_stats(self) -> ResourceStats:
        """
        Get resource statistics.
        
        Returns:
            Resource statistics
        """
        total_gpus = sum(node.gpu_count for node in self._nodes.values())
        used_gpus = sum(alloc.amount for alloc in self._allocations.values() if alloc.resource_type == "gpu")
        
        return ResourceStats(
            total=total_gpus,
            used=used_gpus,
            available=total_gpus - used_gpus,
            utilization=used_gpus / total_gpus if total_gpus > 0 else 0
        )