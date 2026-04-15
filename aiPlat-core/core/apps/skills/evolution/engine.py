"""
Skill Evolution Engine

Main engine for Skill auto-evolution.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from .types import (
    EvolutionType,
    TriggerType,
    TriggerStatus,
    EvolutionTrigger,
    EvolutionSuggestion,
    EvolutionResult,
    EvolutionConfig
)
from .lineage import get_version_lineage, VersionLineage

logger = logging.getLogger(__name__)


class EvolutionEngine:
    """Skill evolution engine"""
    
    def __init__(self, config: Optional[EvolutionConfig] = None):
        self._config = config or EvolutionConfig()
        self._lineage: VersionLineage = get_version_lineage()
        self._pending_triggers: Dict[str, EvolutionTrigger] = {}
        self._last_evolution_time: Dict[str, datetime] = {}
    
    def _can_evolution(self, skill_id: str) -> bool:
        """Check if evolution is allowed (cooldown check)"""
        if skill_id not in self._last_evolution_time:
            return True
        
        elapsed = datetime.utcnow() - self._last_evolution_time[skill_id]
        if elapsed < timedelta(hours=self._config.cooldown_hours):
            logger.warning(f"Skill {skill_id} in cooldown period")
            return False
        
        return True
    
    async def trigger_evolution(
        self,
        skill_id: str,
        trigger_type: TriggerType,
        context: Dict[str, Any]
    ) -> EvolutionResult:
        """Trigger evolution for a skill"""
        # Check cooldown
        if not self._can_evolution(skill_id):
            return EvolutionResult(
                success=False,
                error="Evolution in cooldown period"
            )
        
        # Check max versions
        lineage = await self._lineage.get_lineage(skill_id)
        if len(lineage) >= self._config.max_versions_per_skill:
            return EvolutionResult(
                success=False,
                error="Max versions reached"
            )
        
        # Determine evolution type based on context
        evolution_type = self._determine_evolution_type(trigger_type, context)
        
        try:
            # Create new version
            new_version = await self._lineage.create_version(
                skill_id=skill_id,
                parent_version=lineage[-1].version if lineage else None,
                evolution_type=evolution_type,
                trigger=f"{trigger_type.value}: {context.get('reason', '')}",
                content=context.get("content", "")
            )
            
            # Update last evolution time
            self._last_evolution_time[skill_id] = datetime.utcnow()
            
            logger.info(f"Evolution completed for skill {skill_id}: {new_version.version}")
            
            return EvolutionResult(
                success=True,
                new_version=new_version
            )
            
        except Exception as e:
            logger.error(f"Evolution failed for skill {skill_id}: {e}")
            return EvolutionResult(
                success=False,
                error=str(e)
            )
    
    def _determine_evolution_type(
        self,
        trigger_type: TriggerType,
        context: Dict[str, Any]
    ) -> EvolutionType:
        """Determine evolution type based on trigger and context"""
        if trigger_type == TriggerType.TOOL_DEGRADATION:
            return EvolutionType.FIX
        elif trigger_type == TriggerType.METRIC:
            return EvolutionType.FIX
        elif trigger_type == TriggerType.POST_EXEC:
            if context.get("success", False):
                return EvolutionType.CAPTURED
            else:
                return EvolutionType.FIX
        return EvolutionType.FIX
    
    async def analyze_execution(
        self,
        skill_id: str,
        execution_result: Dict[str, Any]
    ) -> List[EvolutionSuggestion]:
        """Analyze execution result and generate evolution suggestions"""
        suggestions = []
        
        # Check if execution failed
        if not execution_result.get("success", True):
            error_type = execution_result.get("error_type", "unknown")
            
            if error_type in ["timeout", "tool_error"]:
                suggestions.append(EvolutionSuggestion(
                    suggestion_type=EvolutionType.FIX,
                    reason=f"Execution failed: {error_type}",
                    target_skill=skill_id,
                    changes={"timeout": execution_result.get("timeout_increase", 30)},
                    priority=1
                ))
        
        # Check if task was successful but can be improved
        if execution_result.get("success", False):
            # Check token efficiency
            tokens_used = execution_result.get("tokens_used", 0)
            if tokens_used > 10000:
                suggestions.append(EvolutionSuggestion(
                    suggestion_type=EvolutionType.DERIVED,
                    reason="High token usage - can optimize",
                    target_skill=skill_id,
                    changes={"optimize_prompt": True},
                    priority=2
                ))
        
        return suggestions
    
    async def should_derive(
        self,
        skill_id: str,
        context: Dict[str, Any]
    ) -> bool:
        """Determine if skill should be derived"""
        mismatch = context.get("output_mismatch", False)
        unique_scenario = context.get("unique_scenario", False)
        
        return mismatch and unique_scenario
    
    async def should_capture(
        self,
        execution_record: Dict[str, Any]
    ) -> bool:
        """Determine if execution should be captured as new skill"""
        if not execution_record.get("success", False):
            return False
        
        # Check if pattern is reusable
        pattern_score = execution_record.get("pattern_score", 0)
        if pattern_score > 0.7:
            return True
        
        return False
    
    async def should_fix(
        self,
        skill_id: str,
        error: Dict[str, Any]
    ) -> bool:
        """Determine if skill should be fixed"""
        is_recoverable = error.get("is_recoverable", True)
        root_cause_in_skill = error.get("root_cause_in_skill", True)
        
        return is_recoverable and root_cause_in_skill
    
    async def auto_rollback(
        self,
        skill_id: str,
        current_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float]
    ) -> bool:
        """Auto rollback if performance degraded too much"""
        if not self._config.auto_rollback_on_degradation:
            return False
        
        for metric, current in current_metrics.items():
            baseline = baseline_metrics.get(metric, 0)
            if baseline > 0:
                degradation = (baseline - current) / baseline
                if degradation > self._config.degradation_threshold:
                    logger.warning(f"Performance degraded for {skill_id}.{metric}: {degradation:.1%}")
                    await self._lineage.rollback(skill_id, "v-1")
                    return True
        
        return False
    
    def get_pending_triggers(self) -> List[EvolutionTrigger]:
        """Get all pending triggers"""
        return [
            t for t in self._pending_triggers.values()
            if t.status == TriggerStatus.PENDING
        ]
    
    def get_stats(self) -> Dict:
        """Get evolution engine stats"""
        return {
            "pending_triggers": len(self.get_pending_triggers()),
            "skills_evolved": len(self._last_evolution_time),
            "config": {
                "cooldown_hours": self._config.cooldown_hours,
                "max_versions": self._config.max_versions_per_skill
            }
        }


# Global engine instance
_engine: Optional[EvolutionEngine] = None


def get_evolution_engine(config: Optional[EvolutionConfig] = None) -> EvolutionEngine:
    """Get global evolution engine"""
    global _engine
    if _engine is None:
        _engine = EvolutionEngine(config)
    return _engine


__all__ = [
    "EvolutionEngine",
    "get_evolution_engine"
]