"""
Evolution Triggers

Implements the three trigger mechanisms for skill evolution.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from .types import TriggerType, TriggerStatus, EvolutionTrigger
from .engine import get_evolution_engine

logger = logging.getLogger(__name__)


class BaseTrigger:
    """Base class for evolution triggers"""
    
    async def check(self) -> List[EvolutionTrigger]:
        """Check and return pending triggers"""
        raise NotImplementedError


@dataclass
class ToolMetrics:
    """Tool execution metrics"""
    tool_name: str
    success_count: int = 0
    failure_count: int = 0
    last_checked: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total


class PostExecutionTrigger(BaseTrigger):
    """Trigger: Analyze after task execution"""
    
    def __init__(self):
        self._execution_queue: List[Dict] = []
    
    async def enqueue(self, execution_record: Dict):
        """Add execution record to analysis queue"""
        self._execution_queue.append(execution_record)
    
    async def check(self) -> List[EvolutionTrigger]:
        """Check for evolution opportunities"""
        triggers = []
        
        while self._execution_queue:
            record = self._execution_queue.pop(0)
            
            skill_id = record.get("skill_id", "unknown")
            success = record.get("success", False)
            error_type = record.get("error_type")
            
            # Analyze and create trigger if needed
            if not success and error_type:
                trigger = EvolutionTrigger(
                    id=f"post_exec_{datetime.utcnow().timestamp()}",
                    skill_id=skill_id,
                    trigger_type=TriggerType.POST_EXEC,
                    status=TriggerStatus.PENDING,
                    suggestion=f"Execution failed: {error_type}",
                    metadata=record
                )
                triggers.append(trigger)
            
            # Check for capture opportunities
            if success and record.get("pattern_reusable", False):
                trigger = EvolutionTrigger(
                    id=f"capture_{datetime.utcnow().timestamp()}",
                    skill_id=skill_id,
                    trigger_type=TriggerType.POST_EXEC,
                    status=TriggerStatus.PENDING,
                    suggestion="Reusable pattern detected",
                    metadata={"capture": True, **record}
                )
                triggers.append(trigger)
        
        return triggers


class ToolDegradationTrigger(BaseTrigger):
    """Trigger: Detect tool success rate degradation"""
    
    def __init__(self):
        self._tool_metrics: Dict[str, ToolMetrics] = {}
        self._degradation_threshold = 0.2  # 20% drop
    
    async def record_execution(self, tool_name: str, success: bool):
        """Record tool execution result"""
        if tool_name not in self._tool_metrics:
            self._tool_metrics[tool_name] = ToolMetrics(tool_name=tool_name)
        
        metrics = self._tool_metrics[tool_name]
        if success:
            metrics.success_count += 1
        else:
            metrics.failure_count += 1
        metrics.last_checked = datetime.utcnow()
    
    async def check(self) -> List[EvolutionTrigger]:
        """Check for tool degradation"""
        triggers = []
        
        for tool_name, metrics in self._tool_metrics.items():
            # Get baseline (could be from config or initial runs)
            baseline_rate = 0.95  # Assume 95% baseline
            
            if metrics.success_rate < baseline_rate - self._degradation_threshold:
                logger.warning(f"Tool {tool_name} degraded: {metrics.success_rate:.1%}")
                
                # Find skills using this tool
                affected_skills = self._get_skills_using_tool(tool_name)
                
                for skill_id in affected_skills:
                    trigger = EvolutionTrigger(
                        id=f"degradation_{tool_name}_{skill_id}_{datetime.utcnow().timestamp()}",
                        skill_id=skill_id,
                        trigger_type=TriggerType.TOOL_DEGRADATION,
                        status=TriggerStatus.PENDING,
                        suggestion=f"Tool {tool_name} success rate dropped to {metrics.success_rate:.1%}",
                        metadata={
                            "tool": tool_name,
                            "current_rate": metrics.success_rate,
                            "baseline_rate": baseline_rate
                        }
                    )
                    triggers.append(trigger)
        
        return triggers
    
    def _get_skills_using_tool(self, tool_name: str) -> List[str]:
        # In practice, this would query a tool-skill mapping
        # Placeholder: return common skills
        return ["code-review", "bug-fix", "refactor"]


class MetricMonitorTrigger(BaseTrigger):
    """Trigger: Monitor skill metrics and trigger on threshold"""
    
    def __init__(self):
        self._skill_metrics: Dict[str, Dict[str, float]] = {}
        self._check_interval_seconds = 3600  # 1 hour
    
    async def record_metric(self, skill_id: str, metric_name: str, value: float):
        """Record metric for a skill"""
        if skill_id not in self._skill_metrics:
            self._skill_metrics[skill_id] = {}
        self._skill_metrics[skill_id][metric_name] = value
    
    async def check(self) -> List[EvolutionTrigger]:
        """Check metric thresholds"""
        triggers = []
        
        thresholds = {
            "success_rate": 0.6,    # Below 60% success
            "application_rate": 0.1, # Applied less than 10% of the time
            "rollback_rate": 0.3    # Rollback more than 30%
        }
        
        for skill_id, metrics in self._skill_metrics.items():
            for metric_name, threshold in thresholds.items():
                if metric_name in metrics:
                    value = metrics[metric_name]
                    if value < threshold:
                        trigger = EvolutionTrigger(
                            id=f"metric_{skill_id}_{metric_name}_{datetime.utcnow().timestamp()}",
                            skill_id=skill_id,
                            trigger_type=TriggerType.METRIC,
                            status=TriggerStatus.PENDING,
                            suggestion=f"Metric {metric_name} below threshold: {value:.1%} < {threshold:.1%}",
                            metadata={"metric": metric_name, "value": value, "threshold": threshold}
                        )
                        triggers.append(trigger)
        
        return triggers


class TriggerManager:
    """Manages all evolution triggers"""
    
    def __init__(self):
        self._post_exec_trigger = PostExecutionTrigger()
        self._tool_degradation_trigger = ToolDegradationTrigger()
        self._metric_trigger = MetricMonitorTrigger()
        self._engine = get_evolution_engine()
    
    async def trigger_post_exec(self, execution_record: Dict):
        """Trigger analysis after execution"""
        await self._post_exec_trigger.enqueue(execution_record)
    
    async def trigger_tool_execution(self, tool_name: str, success: bool):
        """Record tool execution for degradation detection"""
        await self._tool_degradation_trigger.record_execution(tool_name, success)
    
    async def trigger_metric(self, skill_id: str, metric_name: str, value: float):
        """Record metric for monitoring"""
        await self._metric_trigger.record_metric(skill_id, metric_name, value)
    
    async def check_all_triggers(self) -> List[EvolutionTrigger]:
        """Check all trigger sources"""
        all_triggers = []
        
        # Check each trigger type
        all_triggers.extend(await self._post_exec_trigger.check())
        all_triggers.extend(await self._tool_degradation_trigger.check())
        all_triggers.extend(await self._metric_trigger.check())
        
        # Process triggers
        for trigger in all_triggers:
            result = await self._engine.trigger_evolution(
                skill_id=trigger.skill_id,
                trigger_type=trigger.trigger_type,
                context=trigger.metadata
            )
            
            if result.success:
                logger.info(f"Triggered evolution for {trigger.skill_id}: {trigger.suggestion}")
            else:
                logger.warning(f"Trigger failed for {trigger.skill_id}: {result.error}")
        
        return all_triggers


# Global trigger manager
_trigger_manager: Optional[TriggerManager] = None


def get_trigger_manager() -> TriggerManager:
    """Get global trigger manager"""
    global _trigger_manager
    if _trigger_manager is None:
        _trigger_manager = TriggerManager()
    return _trigger_manager


__all__ = [
    "TriggerManager",
    "PostExecutionTrigger",
    "ToolDegradationTrigger",
    "MetricMonitorTrigger",
    "get_trigger_manager"
]