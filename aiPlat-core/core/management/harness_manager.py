"""
Harness Manager - Manages execution engine

Provides execution engine configuration and monitoring operations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


@dataclass
class HarnessStatus:
    """Harness status"""
    status: str  # healthy, degraded, unhealthy
    components: Dict[str, Dict[str, Any]]
    uptime_seconds: float
    last_check: datetime


@dataclass
class HookConfig:
    """Hook configuration"""
    id: str
    name: str
    type: str  # pre, post
    priority: int
    enabled: bool
    config: Dict[str, Any]


@dataclass
class ExecutionConfig:
    """Execution configuration"""
    max_iterations: int = 25
    timeout_seconds: int = 300
    retry_count: int = 3
    retry_interval_seconds: int = 1
    hooks: List[HookConfig] = field(default_factory=list)


@dataclass
class CoordinatorInfo:
    """Coordinator information"""
    id: str
    pattern: str  # Pipeline, FanOutFanIn, Supervisor, ExpertPool, ProducerReviewer, Hierarchical
    agents: List[str]
    status: str  # active, idle, stopped
    config: Dict[str, Any]
    created_at: datetime


@dataclass
class FeedbackLoopConfig:
    """Feedback loop configuration"""
    local: Dict[str, Any]
    push: Dict[str, Any]
    prod: Dict[str, Any]


@dataclass
class ExecutionLog:
    """Execution log"""
    id: str
    agent: str
    status: str  # pending, running, completed, failed
    start_time: datetime
    end_time: Optional[datetime]
    duration_ms: float
    steps: List[Dict[str, Any]]
    error: Optional[str]


class HarnessManager:
    """
    Harness Manager - Manages execution engine
    
    Provides:
    - Execution configuration
    - Hook management
    - Coordinator management
    - Feedback loop management
    - Execution monitoring
    """
    
    def __init__(self):
        self._config = ExecutionConfig()
        self._hooks: Dict[str, HookConfig] = {}
        self._coordinators: Dict[str, CoordinatorInfo] = {}
        self._feedback_config = FeedbackLoopConfig(
            local={"enabled": True, "max_history": 1000},
            push={"enabled": True, "endpoint": "", "interval_seconds": 60},
            prod={"enabled": True, "canary_percent": 10}
        )
        self._execution_logs: List[ExecutionLog] = []
        self._status = HarnessStatus(
            status="healthy",
            components={
                "execution": {"status": "healthy", "active_loops": 0},
                "coordination": {"status": "healthy", "coordinators": 0},
                "observability": {"status": "healthy", "events": 0},
                "feedback_loops": {"status": "healthy", "feedback_count": 0}
            },
            uptime_seconds=0.0,
            last_check=datetime.utcnow()
        )
    
    async def get_status(self) -> HarnessStatus:
        """Get harness status"""
        self._status.last_check = datetime.utcnow()
        return self._status
    
    async def get_config(self) -> ExecutionConfig:
        """Get execution configuration"""
        return self._config
    
    async def update_config(
        self,
        max_iterations: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        retry_count: Optional[int] = None,
        retry_interval_seconds: Optional[int] = None
    ) -> ExecutionConfig:
        """Update execution configuration"""
        if max_iterations is not None:
            self._config.max_iterations = max_iterations
        if timeout_seconds is not None:
            self._config.timeout_seconds = timeout_seconds
        if retry_count is not None:
            self._config.retry_count = retry_count
        if retry_interval_seconds is not None:
            self._config.retry_interval_seconds = retry_interval_seconds
        
        return self._config
    
    async def add_hook(
        self,
        name: str,
        hook_type: str,
        priority: int,
        enabled: bool = True,
        config: Optional[Dict[str, Any]] = None
    ) -> HookConfig:
        """Add hook"""
        hook_id = f"hook-{uuid.uuid4().hex[:8]}"
        
        hook = HookConfig(
            id=hook_id,
            name=name,
            type=hook_type,
            priority=priority,
            enabled=enabled,
            config=config or {}
        )
        
        self._hooks[hook_id] = hook
        self._config.hooks.append(hook)
        
        return hook
    
    async def get_hooks(self) -> List[HookConfig]:
        """Get all hooks"""
        return list(self._hooks.values())
    
    async def update_hook(
        self,
        hook_id: str,
        name: Optional[str] = None,
        priority: Optional[int] = None,
        enabled: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[HookConfig]:
        """Update hook"""
        hook = self._hooks.get(hook_id)
        if not hook:
            return None
        
        if name:
            hook.name = name
        if priority is not None:
            hook.priority = priority
        if enabled is not None:
            hook.enabled = enabled
        if config:
            hook.config.update(config)
        
        return hook
    
    async def delete_hook(self, hook_id: str) -> bool:
        """Delete hook"""
        if hook_id not in self._hooks:
            return False
        
        del self._hooks[hook_id]
        self._config.hooks = [h for h in self._config.hooks if h.id != hook_id]
        
        return True
    
    async def create_coordinator(
        self,
        pattern: str,
        agents: List[str],
        config: Optional[Dict[str, Any]] = None
    ) -> CoordinatorInfo:
        """Create coordinator"""
        coordinator_id = f"coord-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        coordinator = CoordinatorInfo(
            id=coordinator_id,
            pattern=pattern,
            agents=agents,
            status="idle",
            config=config or {},
            created_at=now
        )
        
        self._coordinators[coordinator_id] = coordinator
        
        return coordinator
    
    async def get_coordinator(self, coordinator_id: str) -> Optional[CoordinatorInfo]:
        """Get coordinator by ID"""
        return self._coordinators.get(coordinator_id)
    
    async def list_coordinators(
        self,
        pattern: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[CoordinatorInfo]:
        """List coordinators"""
        coordinators = list(self._coordinators.values())
        
        if pattern:
            coordinators = [c for c in coordinators if c.pattern == pattern]
        if status:
            coordinators = [c for c in coordinators if c.status == status]
        
        return coordinators
    
    async def delete_coordinator(self, coordinator_id: str) -> bool:
        """Delete coordinator"""
        if coordinator_id not in self._coordinators:
            return False
        
        del self._coordinators[coordinator_id]
        return True
    
    async def get_feedback_config(self) -> FeedbackLoopConfig:
        """Get feedback loop configuration"""
        return self._feedback_config
    
    async def update_feedback_config(
        self,
        local: Optional[Dict[str, Any]] = None,
        push: Optional[Dict[str, Any]] = None,
        prod: Optional[Dict[str, Any]] = None
    ) -> FeedbackLoopConfig:
        """Update feedback loop configuration"""
        if local:
            self._feedback_config.local.update(local)
        if push:
            self._feedback_config.push.update(push)
        if prod:
            self._feedback_config.prod.update(prod)
        
        return self._feedback_config
    
    async def record_execution(
        self,
        agent: str,
        status: str,
        steps: List[Dict[str, Any]],
        duration_ms: float,
        error: Optional[str] = None
    ) -> str:
        """Record execution"""
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        log = ExecutionLog(
            id=execution_id,
            agent=agent,
            status=status,
            start_time=now,
            end_time=now if status in ["completed", "failed"] else None,
            duration_ms=duration_ms,
            steps=steps,
            error=error
        )
        
        self._execution_logs.append(log)
        
        return execution_id
    
    async def get_execution_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        agent: Optional[str] = None
    ) -> List[ExecutionLog]:
        """Get execution logs"""
        logs = self._execution_logs
        
        if status:
            logs = [l for l in logs if l.status == status]
        if agent:
            logs = [l for l in logs if l.agent == agent]
        
        return logs[offset:offset + limit]
    
    async def get_execution(self, execution_id: str) -> Optional[ExecutionLog]:
        """Get execution by ID"""
        for log in self._execution_logs:
            if log.id == execution_id:
                return log
        return None
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get harness metrics"""
        return {
            "execution": {
                "active_loops": sum(1 for l in self._execution_logs if l.status == "running"),
                "total_executions": len(self._execution_logs),
                "completed": sum(1 for l in self._execution_logs if l.status == "completed"),
                "failed": sum(1 for l in self._execution_logs if l.status == "failed")
            },
            "coordination": {
                "active_coordinators": sum(1 for c in self._coordinators.values() if c.status == "active"),
                "total_coordinators": len(self._coordinators)
            },
            "hooks": {
                "total_hooks": len(self._hooks),
                "enabled_hooks": sum(1 for h in self._hooks.values() if h.enabled)
            }
        }