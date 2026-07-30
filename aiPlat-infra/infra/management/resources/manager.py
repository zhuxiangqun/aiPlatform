"""
Resources Manager

Manages compute resources including GPU, CPU, and memory.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics
from ..schemas import ResourceStats, NodeInfo, AllocatedResource
from datetime import datetime, timezone
import logging


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
                return Status.DISABLED
            
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
        """获取资源指标（实时系统采集）。"""
        metrics = []
        timestamp = datetime.now(timezone.utc).timestamp()

        try:
            import psutil

            # CPU 使用率（interval=0.1 非阻塞采样）
            cpu_pct = psutil.cpu_percent(interval=0.1)
            metrics.append(Metrics(
                name="resources.cpu_usage", value=round(cpu_pct / 100, 3),
                unit="ratio", timestamp=timestamp,
                labels={"module": "resources", "cpu_count": str(psutil.cpu_count() or 1)}
            ))

            # 内存使用率
            mem = psutil.virtual_memory()
            metrics.append(Metrics(
                name="resources.memory_usage", value=round(mem.percent / 100, 3),
                unit="ratio", timestamp=timestamp,
                labels={"module": "resources", "total_gb": f"{mem.total/1e9:.1f}", "available_gb": f"{mem.available/1e9:.1f}"}
            ))

            # 磁盘使用率
            disk = psutil.disk_usage("/")
            metrics.append(Metrics(
                name="resources.disk_usage", value=round(disk.percent / 100, 3),
                unit="ratio", timestamp=timestamp,
                labels={"module": "resources", "total_gb": f"{disk.total/1e9:.1f}", "free_gb": f"{disk.free/1e9:.1f}"}
            ))

            # GPU 信息（Apple Silicon 统一内存 / NVIDIA 独立显存）
            try:
                from infra.management.model.manager import collect_platform_resources
                pres = collect_platform_resources()
                gpu_label = pres.gpu_vendor or "none"
                vram_total = pres.vram_bytes or 0
                vram_free = pres.ram_bytes or 0  # Apple 统一内存下 vram==ram
                if pres.gpu_compatible:
                    if pres.gpu_vendor == "apple":
                        # 统一内存：占用估算 = 总内存 × (已用比例)
                        used_pct = mem.percent / 100 if mem.total > 0 else 0
                        gpu_mem_used = int(vram_total * used_pct)
                        gpu_mem_total = vram_total
                    else:
                        gpu_mem_used = max(vram_total - vram_free, 0)
                        gpu_mem_total = vram_total
                    metrics.append(Metrics(
                        name="resources.gpu_utilization", value=round(mem.percent / 100, 3),
                        unit="ratio", timestamp=timestamp,
                        labels={"module": "resources", "gpu_vendor": gpu_label}
                    ))
                    metrics.append(Metrics(
                        name="resources.gpu_memory_used", value=gpu_mem_used,
                        unit="bytes", timestamp=timestamp,
                        labels={"module": "resources", "total_bytes": str(gpu_mem_total), "gpu_vendor": gpu_label}
                    ))
            except Exception:
                pass  # noqa: intentional — best-effort non-critical operation

        except ImportError:
            pass  # psutil 不可用，跳过实时指标  # noqa: optional-dependency

        # 活跃分配数
        metrics.append(Metrics(
            name="resources.allocations_active", value=len(self._allocations),
            unit="count", timestamp=timestamp,
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
            elif status == Status.DISABLED:
                return HealthStatus(
                    status=status,
                    message="Resource nodes not configured (disabled)",
                    details={"nodes": 0}
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
        allocation_id = f"alloc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        allocation = AllocatedResource(
            allocation_id=allocation_id,
            resource_type=request.get("resource_type", "gpu"),
            amount=request.get("amount", 1),
            allocated_at=datetime.now(timezone.utc),
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

