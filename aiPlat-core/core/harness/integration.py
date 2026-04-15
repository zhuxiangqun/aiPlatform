"""
Harness Integration Module

Provides a unified entry point for the Harness framework.
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from .interfaces import (
    IAgent,
    ITool,
    ISkill,
    ILoop,
    ICoordinator,
)
from .execution import (
    BaseLoop,
    ReActLoop,
    PlanExecuteLoop,
    create_loop,
)
from .coordination import (
    create_pattern,
    create_coordinator,
    create_detector,
)
from .observability import (
    MonitoringSystem,
    MetricsCollector,
    EventBus,
    AlertManager,
)
from .feedback_loops import (
    LocalFeedbackLoop,
    PushManager,
    ProductionFeedbackLoop,
    EvolutionEngine,
)
from .memory import (
    MemoryBase,
    MemoryScope,
    ShortTermMemory,
    LongTermMemory,
    SessionManager,
)


@dataclass
class HarnessConfig:
    """Harness configuration"""
    enable_monitoring: bool = True
    enable_observability: bool = True
    enable_feedback_loops: bool = True
    enable_memory: bool = True
    enable_evolution: bool = True
    
    monitoring_config: Dict[str, Any] = field(default_factory=dict)
    memory_config: Dict[str, Any] = field(default_factory=dict)
    feedback_config: Dict[str, Any] = field(default_factory=dict)


class HarnessIntegration:
    """
    Harness Integration - Unified Entry Point
    
    Provides centralized access to all Harness components.
    """
    
    _instance: Optional["HarnessIntegration"] = None
    
    def __init__(self, config: Optional[HarnessConfig] = None):
        self._config = config or HarnessConfig()
        self._initialized = False
        
        self._monitoring: Optional[MonitoringSystem] = None
        self._metrics: Optional[MetricsCollector] = None
        self._event_bus: Optional[EventBus] = None
        self._alert_manager: Optional[AlertManager] = None
        self._feedback: Optional[LocalFeedbackLoop] = None
        self._push_manager: Optional[PushManager] = None
        self._prod_feedback: Optional[ProductionFeedbackLoop] = None
        self._evolution: Optional[EvolutionEngine] = None
        self._memory: Optional[MemoryBase] = None
        self._session_manager: Optional[SessionManager] = None
    
    @classmethod
    def get_instance(cls) -> "HarnessIntegration":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def initialize(cls, config: Optional[HarnessConfig] = None) -> "HarnessIntegration":
        instance = cls.get_instance()
        instance._config = config or HarnessConfig()
        instance._setup()
        return instance
    
    def _setup(self):
        if self._initialized:
            return
        
        if self._config.enable_observability:
            self._monitoring = MonitoringSystem.get_instance()
            self._metrics = MetricsCollector.get_instance()
            self._event_bus = EventBus.get_instance()
            self._alert_manager = AlertManager.get_instance()
        
        if self._config.enable_feedback_loops:
            self._feedback = LocalFeedbackLoop()
            self._push_manager = PushManager()
            self._prod_feedback = ProductionFeedbackLoop()
            if self._config.enable_evolution:
                self._evolution = EvolutionEngine()
        
        if self._config.enable_memory:
            self._memory = ShortTermMemory(self._config.memory_config)
            self._session_manager = SessionManager()
        
        self._initialized = True
    
    @property
    def config(self) -> HarnessConfig:
        return self._config
    
    @property
    def monitoring(self) -> Optional[MonitoringSystem]:
        return self._monitoring
    
    @property
    def metrics(self) -> Optional[MetricsCollector]:
        return self._metrics
    
    @property
    def event_bus(self) -> Optional[EventBus]:
        return self._event_bus
    
    @property
    def alert_manager(self) -> Optional[AlertManager]:
        return self._alert_manager
    
    @property
    def feedback(self) -> Optional[LocalFeedbackLoop]:
        return self._feedback
    
    @property
    def push_manager(self) -> Optional[PushManager]:
        return self._push_manager
    
    @property
    def prod_feedback(self) -> Optional[ProductionFeedbackLoop]:
        return self._prod_feedback
    
    @property
    def evolution(self) -> Optional[EvolutionEngine]:
        return self._evolution
    
    @property
    def memory(self) -> Optional[MemoryBase]:
        return self._memory
    
    @property
    def session_manager(self) -> Optional[SessionManager]:
        return self._session_manager
    
    def create_agent_loop(
        self,
        agent: IAgent,
        loop_type: str = "react",
        **kwargs,
    ) -> ILoop:
        return create_loop(loop_type, agent=agent, **kwargs)
    
    def create_coordinator_pattern(
        self,
        pattern_type: str = "pipeline",
        **kwargs,
    ):
        return create_pattern(pattern_type, **kwargs)
    
    def create_convergence_detector(
        self,
        detector_type: str = "exact",
        **kwargs,
    ):
        return create_detector(detector_type, **kwargs)
    
    async def start(self):
        if self._config.enable_observability and self._monitoring:
            await self._monitoring.start_monitoring()
        if self._config.enable_feedback_loops and self._push_manager:
            await self._push_manager.start()
    
    async def stop(self):
        if self._config.enable_observability and self._monitoring:
            self._monitoring.stop_monitoring()
        if self._config.enable_feedback_loops and self._push_manager:
            await self._push_manager.stop()
    
    async def reset(self):
        if self._metrics:
            self._metrics.reset()
        if self._feedback:
            self._feedback.clear()
        if self._memory:
            await self._memory.clear(MemoryScope.SESSION)


def create_harness(config: Optional[HarnessConfig] = None) -> HarnessIntegration:
    return HarnessIntegration.initialize(config)


def get_harness() -> HarnessIntegration:
    return HarnessIntegration.get_instance()


__all__ = [
    "HarnessConfig",
    "HarnessIntegration",
    "create_harness",
    "get_harness",
]