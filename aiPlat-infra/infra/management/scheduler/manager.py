"""
Scheduler Manager

Manages GPU resource quotas, scheduling policies, and task queues.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from ..schemas import QuotaInfo, PolicyInfo, TaskInfo, AutoscalingPolicy
from datetime import datetime
import time


def get_real_gpu_info() -> Dict[str, Any]:
    """Get real GPU information from system."""
    result = {
        "total_gpus": 0,
        "used_gpus": 0,
        "available_gpus": 0,
        "gpu_details": []
    }
    
    try:
        import subprocess
        
        # Try to get GPUinfo using system_profiler (macOS)
        result_subprocess = subprocess.run(
            ['system_profiler', 'SPDisplaysDataType'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result_subprocess.returncode == 0:
            output = result_subprocess.stdout
            # Count GPU occurrences
            gpu_count = output.lower().count('chipset model:') or output.lower().count('vendor:')
            
            # Check for Apple Silicon
            if 'apple' in output.lower() or 'm1' in output.lower() or 'm2' in output.lower() or 'm3' in output.lower():
                gpu_count = 1# Apple Silicon has unified GPU
            
            result["total_gpus"] = max(gpu_count, 1)
            result["available_gpus"] = result["total_gpus"]
            result["gpu_details"].append({
                "model": "Apple Silicon" if "apple" in output.lower() else "Unknown",
                "count": result["total_gpus"]
            })
    except Exception:
        # Default to 1 GPUif detection fails
        result["total_gpus"] = 1
        result["available_gpus"] = 1
    
    return result


class SchedulerManager(ManagementBase):
    """
    Manager for GPU scheduling and task queues.
    
    Provides resource quota management, scheduling policies, and task queue management.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._quotas: Dict[str, QuotaInfo] = {}
        self._policies: Dict[str, PolicyInfo] = {}
        self._tasks: Dict[str, TaskInfo] = {}
        self._autoscaling_policies: Dict[str, AutoscalingPolicy] = {}
        self._total_gpu_quota = 0
        self._used_gpu_quota = 0
        self._standalone_mode = config.get("standalone_mode", True) if config else True
        
        if self._standalone_mode:
            self._init_from_system()
    
    def _init_from_system(self):
        """Initialize from real system GPU info."""
        gpu_info = get_real_gpu_info()
        
        self._total_gpu_quota = gpu_info["total_gpus"]
        self._used_gpu_quota =0# No tasks running by default
        self._available_gpus = gpu_info["available_gpus"]
        
        # Create a single default quota for the system
        self._quotas = {
            "system": QuotaInfo(
                id="quota-system",
                name="system",
                gpu_quota=gpu_info["total_gpus"],
                gpu_used=0,
                team="system",
                status="Active",
                created_at=datetime.now()
            )
        }
        
        # Default scheduling policy
        self._policies = {
            "default": PolicyInfo(
                id="policy-default",
                name="default-schedule",
                type="fair",
                priority=1,
                node_selector={},
                status="Active"
            )
        }
        
        # No autoscaling in standalone mode by default
        self._autoscaling_policies = {}
    
    async def get_status(self) -> Status:
        """Get scheduler module status."""
        try:
            if not self._quotas or not self._policies:
                return Status.UNKNOWN
            
            pending_tasks = sum(
                1 for task in self._tasks.values()
                if task.status == "pending"
            )
            
            total_tasks = len(self._tasks)
            
            if pending_tasks > total_tasks * 0.5:
                return Status.DEGRADED
            elif pending_tasks > 0:
                return Status.HEALTHY
            else:
                return Status.HEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get scheduler metrics."""
        metrics = []
        timestamp = time.time()
        
        metrics.append(Metrics(
            name="scheduler.quota_total",
            value=self._total_gpu_quota,
            unit="count",
            timestamp=timestamp,
            labels={"module": "scheduler"}
        ))
        
        metrics.append(Metrics(
            name="scheduler.quota_used",
            value=self._used_gpu_quota,
            unit="count",
            timestamp=timestamp,
            labels={"module": "scheduler"}
        ))
        
        metrics.append(Metrics(
            name="scheduler.quota_available",
            value=self._total_gpu_quota - self._used_gpu_quota,
            unit="count",
            timestamp=timestamp,
            labels={"module": "scheduler"}
        ))
        
        pending_tasks = sum(1 for task in self._tasks.values() if task.status == "pending")
        running_tasks = sum(1 for task in self._tasks.values() if task.status == "running")
        
        metrics.append(Metrics(
            name="scheduler.tasks_pending",
            value=pending_tasks,
            unit="count",
            timestamp=timestamp,
            labels={"module": "scheduler"}
        ))
        
        metrics.append(Metrics(
            name="scheduler.tasks_running",
            value=running_tasks,
            unit="count",
            timestamp=timestamp,
            labels={"module": "scheduler"}
        ))
        
        for quota_name, quota in self._quotas.items():
            metrics.append(Metrics(
                name="scheduler.quota_usage",
                value=quota.gpu_used / quota.gpu_quota if quota.gpu_quota > 0 else 0,
                unit="ratio",
                timestamp=timestamp,
                labels={"quota": quota_name, "module": "scheduler"}
            ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform scheduler health check."""
        issues = []
        details = {
            "total_quotas": len(self._quotas),
            "total_policies": len(self._policies),
            "total_tasks": len(self._tasks),
            "quota_utilization": self._used_gpu_quota / self._total_gpu_quota if self._total_gpu_quota > 0 else 0
        }
        
        for quota_name, quota in self._quotas.items():
            if quota.gpu_used >= quota.gpu_quota:
                issues.append(f"Quota {quota_name} is exhausted")
        
        for task_id, task in self._tasks.items():
            if task.status == "pending":
                wait_time = (datetime.now() - task.submitted_at).total_seconds()
                if wait_time > 3600:
                    issues.append(f"Task {task_id} has been pending for {wait_time}s")
        
        if len(issues) == 0:
            return HealthStatus(
                status=Status.HEALTHY,
                message="Scheduler is healthy",
                details=details
            )
        elif len(issues) < len(self._quotas):
            return HealthStatus(
                status=Status.DEGRADED,
                message=f"{len(issues)} scheduler issues detected",
                details={**details, "issues": issues}
            )
        else:
            return HealthStatus(
                status=Status.UNHEALTHY,
                message="Critical scheduler failures detected",
                details={**details, "issues": issues}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get scheduler configuration."""
        return {
            "kubernetes_api": self._get_config_value("kubernetes_api", "https://k8s-api.example.com"),
            "default_scheduler": self._get_config_value("default_scheduler", "default-scheduler"),
            "gpu_scheduler": self._get_config_value("gpu_scheduler", "nvidia-gpu-scheduler"),
            "default_priority": self._get_config_value("default_priority", 0),
            "max_queue_size": self._get_config_value("max_queue_size", 1000)
        }
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update scheduler configuration."""
        if "kubernetes_api" in config:
            self.config["kubernetes_api"] = config["kubernetes_api"]
        if "default_scheduler" in config:
            self.config["default_scheduler"] = config["default_scheduler"]
        if "gpu_scheduler" in config:
            self.config["gpu_scheduler"] = config["gpu_scheduler"]
    
    async def diagnose(self) -> DiagnosisResult:
        """Run diagnostic checks for scheduler."""
        issues = []
        recommendations = []
        details = {}
        
        try:
            status = await self.get_status()
            details["status"] = status.value
            
            if status == Status.UNHEALTHY:
                issues.append("Scheduler module is unhealthy")
                recommendations.append("Check Kubernetes scheduler status")
                recommendations.append("Verify resource quotas are properly configured")
            
            health = await self.health_check()
            details["health"] = health.message
            
            if health.status == Status.DEGRADED:
                issues.append(f"Scheduler health degraded: {health.message}")
                recommendations.append("Review pending tasks and quota allocations")
            
            metrics = await self.get_metrics()
            details["metrics_count"] = len(metrics)
            
            quota_utilization = self._used_gpu_quota / self._total_gpu_quota if self._total_gpu_quota > 0 else 0
            if quota_utilization > 0.9:
                issues.append(f"High quota utilization: {quota_utilization:.2%}")
                recommendations.append("Consider increasing GPU quota or optimizing resource usage")
            
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
                recommendations=["Check scheduler configuration and connectivity"],
                details={"error": str(e)}
            )
    
    async def list_quotas(self) -> List[QuotaInfo]:
        """
        List all resource quotas.
        
        Returns:
            List[QuotaInfo]: List of quota information
        """
        return list(self._quotas.values())
    
    async def get_quota(self, quota_id: str) -> Optional[QuotaInfo]:
        """
        Get quota by ID.
        
        Args:
            quota_id: Quota ID
            
        Returns:
            QuotaInfo or None if not found
        """
        return self._quotas.get(quota_id)
    
    async def create_quota(self, config: Dict[str, Any]) -> QuotaInfo:
        """
        Create a new resource quota.
        
        Args:
            config: Quota configuration
            
        Returns:
            QuotaInfo: Created quota information
        """
        quota_name = config.get("name", f"quota-{len(self._quotas) + 1}")
        
        quota = QuotaInfo(
            id=f"quota-{len(self._quotas) + 1}",
            name=quota_name,
            gpu_quota=config.get("gpu_quota", 0),
            gpu_used=0,
            team=config.get("team", ""),
            status="active",
            created_at=datetime.now()
        )
        
        self._quotas[quota.id] = quota
        self._total_gpu_quota += quota.gpu_quota
        
        return quota
    
    async def update_quota(self, quota_id: str, config: Dict[str, Any]) -> Optional[QuotaInfo]:
        """
        Update resource quota.
        
        Args:
            quota_id: Quota ID
            config: New configuration
            
        Returns:
            Updated QuotaInfo or None if not found
        """
        if quota_id in self._quotas:
            old_quota = self._quotas[quota_id].gpu_quota
            self._quotas[quota_id].gpu_quota = config.get("gpu_quota", old_quota)
            if "name" in config:
                self._quotas[quota_id].name = config["name"]
            if "team" in config:
                self._quotas[quota_id].team = config["team"]
            
            self._total_gpu_quota = self._total_gpu_quota - old_quota + self._quotas[quota_id].gpu_quota
            return self._quotas[quota_id]
        return None
    
    async def delete_quota(self, quota_id: str) -> bool:
        """
        Delete resource quota.
        
        Args:
            quota_id: Quota ID
            
        Returns:
            True if deleted, False if not found
        """
        if quota_id in self._quotas:
            self._total_gpu_quota -= self._quotas[quota_id].gpu_quota
            del self._quotas[quota_id]
            return True
        return False
    
    async def list_policies(self) -> List[PolicyInfo]:
        """
        List all scheduling policies.
        
        Returns:
            List[PolicyInfo]: List of policy information
        """
        return list(self._policies.values())
    
    async def get_policy(self, policy_id: str) -> Optional[PolicyInfo]:
        """
        Get policy by ID.
        
        Args:
            policy_id: Policy ID
            
        Returns:
            PolicyInfo or None if not found
        """
        return self._policies.get(policy_id)
    
    async def create_policy(self, config: Dict[str, Any]) -> PolicyInfo:
        """
        Create a new scheduling policy.
        
        Args:
            config: Policy configuration
            
        Returns:
            PolicyInfo: Created policy information
        """
        policy_name = config.get("name", f"policy-{len(self._policies) + 1}")
        
        policy = PolicyInfo(
            id=f"policy-{len(self._policies) + 1}",
            name=policy_name,
            type=config.get("type", "default"),
            priority=config.get("priority", 0),
            node_selector=config.get("node_selector", {}),
            status="enabled"
        )
        
        self._policies[policy.id] = policy
        
        return policy
    
    async def update_policy(self, policy_id: str, config: Dict[str, Any]) -> None:
        """
        Update scheduling policy.
        
        Args:
            policy_id: Policy ID
            config: New configuration
        """
        if policy_id in self._policies:
            if "priority" in config:
                self._policies[policy_id].priority = config["priority"]
            if "node_selector" in config:
                self._policies[policy_id].node_selector = config["node_selector"]
            if "status" in config:
                self._policies[policy_id].status = config["status"]
    
    async def delete_policy(self, policy_id: str) -> None:
        """
        Delete scheduling policy.
        
        Args:
            policy_id: Policy ID
        """
        if policy_id in self._policies:
            del self._policies[policy_id]
    
    async def list_tasks(self, queue: str = None) -> List[TaskInfo]:
        """
        List all tasks.
        
        Args:
            queue: Filter by queue (optional)
            
        Returns:
            List[TaskInfo]: List of task information
        """
        tasks = list(self._tasks.values())
        
        if queue:
            tasks = [t for t in tasks if t.queue == queue]
        
        return tasks
    
    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """
        Get task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            TaskInfo or None if not found
        """
        return self._tasks.get(task_id)
    
    async def submit_task(self, config: Dict[str, Any]) -> TaskInfo:
        """
        Submit a new task to the queue.
        
        Args:
            config: Task configuration
            
        Returns:
            TaskInfo: Submitted task information
        """
        task_name = config.get("name", f"task-{len(self._tasks) + 1}")
        
        task = TaskInfo(
            id=f"task-{len(self._tasks) + 1}",
            name=task_name,
            gpu_count=config.get("gpu_count", 1),
            gpu_type=config.get("gpu_type", "A100"),
            queue=config.get("queue", "default"),
            priority=config.get("priority", 0),
            status="pending",
            position=len([t for t in self._tasks.values() if t.status == "pending"]) + 1,
            estimated_wait_time=0,
            submitter=config.get("submitter", "system"),
            submitted_at=datetime.now()
        )
        
        self._tasks[task.id] = task
        
        return task
    
    async def create_task(self, config: Dict[str, Any]) -> TaskInfo:
        """Alias for submit_task."""
        return await self.submit_task(config)
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if cancelled, False if not found
        """
        if task_id in self._tasks:
            self._tasks[task_id].status = "cancelled"
            return True
        return False
    
    async def get_queue_status(self, queue: str = "default") -> Dict[str, Any]:
        """
        Get queue status.
        
        Args:
            queue: Queue name
            
        Returns:
            Dict: Queue status
        """
        queue_tasks = [t for t in self._tasks.values() if t.queue == queue]
        
        return {
            "queue": queue,
            "total_tasks": len(queue_tasks),
            "pending": len([t for t in queue_tasks if t.status == "pending"]),
            "running": len([t for t in queue_tasks if t.status == "running"]),
            "completed": len([t for t in queue_tasks if t.status == "completed"]),
            "failed": len([t for t in queue_tasks if t.status == "failed"])
        }
    
    async def list_autoscaling_policies(self) -> List[AutoscalingPolicy]:
        """
        List all autoscaling policies.
        
        Returns:
            List[AutoscalingPolicy]: List of autoscaling policies
        """
        return list(self._autoscaling_policies.values())
    
    async def get_autoscaling_policy(self, service_name: str) -> Optional[AutoscalingPolicy]:
        """
        Get autoscaling policy for a service.
        
        Args:
            service_name: Service name
            
        Returns:
            AutoscalingPolicy or None if not found
        """
        for policy in self._autoscaling_policies.values():
            if policy.service == service_name:
                return policy
        return None
    
    async def create_autoscaling(self, config: Dict[str, Any]) -> AutoscalingPolicy:
        """
        Create autoscaling policy.
        
        Args:
            config: Autoscaling configuration
            
        Returns:
            AutoscalingPolicy: Created autoscaling policy
        """
        service_name = config.get("service", "")
        
        policy = AutoscalingPolicy(
            id=f"autoscaling-{len(self._autoscaling_policies) + 1}",
            service=service_name,
            type=config.get("type", "HPA"),
            min_replicas=config.get("min_replicas", 2),
            max_replicas=config.get("max_replicas", 10),
            current_replicas=config.get("current_replicas", 2),
            target_replicas=config.get("current_replicas", 2),
            metrics=config.get("metrics", []),
            status="running"
        )
        
        self._autoscaling_policies[policy.id] = policy
        
        return policy
    
    async def create_autoscaling_policy(self, config: Dict[str, Any]) -> AutoscalingPolicy:
        """Alias for create_autoscaling."""
        return await self.create_autoscaling(config)
    
    async def update_autoscaling(self, service_name: str, config: Dict[str, Any]) -> None:
        """
        Update autoscaling policy.
        
        Args:
            service_name: Service name
            config: New configuration
        """
        policy = await self.get_autoscaling_policy(service_name)
        if policy:
            self._autoscaling_policies[policy.id].min_replicas = config.get("min_replicas", policy.min_replicas)
            self._autoscaling_policies[policy.id].max_replicas = config.get("max_replicas", policy.max_replicas)
            self._autoscaling_policies[policy.id].metrics = config.get("metrics", policy.metrics)
    
    async def get_autoscaling_history(
        self,
        service_name: str = None,
        start_time: str = None,
        end_time: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get autoscaling history for a service.
        
        Args:
            service_name: Service name (optional)
            start_time: Start time filter (optional)
            end_time: End time filter (optional)
            
        Returns:
            List[Dict]: Autoscaling history
        """
        return []