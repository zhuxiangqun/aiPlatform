"""
Knowledge Evolution Module

Provides knowledge evolution and learning capabilities.
"""

from typing import Any, Dict, List, Optional, Tuple, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class EvolutionType(Enum):
    """Evolution types"""
    QUALITY_IMPROVEMENT = "quality_improvement"
    MERGE = "merge"
    SPLIT = "split"
    DEPRECATE = "deprecate"
    VALIDATE = "validate"
    EXTEND = "extend"


class EvolutionStatus(Enum):
    """Evolution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class EvolutionTrigger:
    """Triggers for knowledge evolution"""
    low_confidence: float = 0.5
    outdated_days: int = 30
    duplicate_threshold: float = 0.95
    usage_frequency_min: int = 3
    error_rate_max: float = 0.1


@dataclass
class EvolutionRecord:
    """Record of an evolution action"""
    id: str
    type: EvolutionType
    source_ids: List[str]
    result_id: Optional[str] = None
    status: EvolutionStatus = EvolutionStatus.PENDING
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "source_ids": self.source_ids,
            "result_id": self.result_id,
            "status": self.status.value,
            "reason": self.reason,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class KnowledgeEvolution:
    """Manages knowledge evolution"""
    
    def __init__(self, trigger: Optional[EvolutionTrigger] = None):
        self._trigger = trigger or EvolutionTrigger()
        self._history: List[EvolutionRecord] = []
        self._pending: List[EvolutionRecord] = []
    
    def should_evolve(
        self,
        entry: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[EvolutionType]]:
        confidence = entry.get("confidence", 1.0)
        if confidence < self._trigger.low_confidence:
            return True, EvolutionType.QUALITY_IMPROVEMENT
        
        updated_at = entry.get("updated_at")
        if updated_at:
            if isinstance(updated_at, str):
                updated_at = datetime.fromisoformat(updated_at)
            days_since_update = (datetime.now() - updated_at).days
            if days_since_update > self._trigger.outdated_days:
                return True, EvolutionType.VALIDATE
        
        if metrics:
            error_rate = metrics.get("error_rate", 0)
            if error_rate > self._trigger.error_rate_max:
                return True, EvolutionType.QUALITY_IMPROVEMENT
        
        return False, None
    
    def check_duplicates(
        self,
        entries: List[Dict[str, Any]],
        similarity_func: Callable[[Dict, Dict], float],
    ) -> List[Tuple[int, int]]:
        duplicates = []
        for i, entry1 in enumerate(entries):
            for j, entry2 in enumerate(entries):
                if i < j:
                    similarity = similarity_func(entry1, entry2)
                    if similarity >= self._trigger.duplicate_threshold:
                        duplicates.append((i, j))
        return duplicates
    
    async def propose_merge(
        self,
        entry_ids: List[str],
        reason: str = "",
    ) -> EvolutionRecord:
        import uuid
        record = EvolutionRecord(
            id=str(uuid.uuid4()),
            type=EvolutionType.MERGE,
            source_ids=entry_ids,
            reason=reason,
        )
        self._pending.append(record)
        return record
    
    async def propose_split(
        self,
        entry_id: str,
        reason: str = "",
    ) -> EvolutionRecord:
        import uuid
        record = EvolutionRecord(
            id=str(uuid.uuid4()),
            type=EvolutionType.SPLIT,
            source_ids=[entry_id],
            reason=reason,
        )
        self._pending.append(record)
        return record
    
    async def propose_deprecate(
        self,
        entry_id: str,
        reason: str = "",
    ) -> EvolutionRecord:
        import uuid
        record = EvolutionRecord(
            id=str(uuid.uuid4()),
            type=EvolutionType.DEPRECATE,
            source_ids=[entry_id],
            reason=reason,
        )
        self._pending.append(record)
        return record
    
    async def execute_evolution(
        self,
        record: EvolutionRecord,
        executor: Callable[[EvolutionRecord], Awaitable[Optional[str]]],
    ) -> bool:
        record.status = EvolutionStatus.IN_PROGRESS
        try:
            result_id = await executor(record)
            record.result_id = result_id
            record.status = EvolutionStatus.COMPLETED
            record.completed_at = datetime.now()
            self._history.append(record)
            if record in self._pending:
                self._pending.remove(record)
            return True
        except Exception as e:
            record.status = EvolutionStatus.FAILED
            record.reason = f"{record.reason}\nError: {str(e)}"
            self._history.append(record)
            if record in self._pending:
                self._pending.remove(record)
            return False
    
    async def rollback(self, record_id: str) -> bool:
        for record in self._history:
            if record.id == record_id and record.status == EvolutionStatus.COMPLETED:
                record.status = EvolutionStatus.ROLLED_BACK
                return True
        return False
    
    def get_pending(self) -> List[EvolutionRecord]:
        return list(self._pending)
    
    def get_history(
        self,
        limit: int = 100,
        type_filter: Optional[EvolutionType] = None,
    ) -> List[EvolutionRecord]:
        history = self._history
        if type_filter:
            history = [r for r in history if r.type == type_filter]
        return history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        by_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        
        for record in self._history:
            by_type[record.type.value] = by_type.get(record.type.value, 0) + 1
            by_status[record.status.value] = by_status.get(record.status.value, 0) + 1
        
        return {
            "total_evolutions": total,
            "pending_count": len(self._pending),
            "by_type": by_type,
            "by_status": by_status,
        }
    
    def clear_history(self):
        self._history.clear()
        self._pending.clear()


def create_evolution(trigger: Optional[EvolutionTrigger] = None) -> KnowledgeEvolution:
    return KnowledgeEvolution(trigger)


__all__ = [
    "EvolutionType",
    "EvolutionStatus",
    "EvolutionTrigger",
    "EvolutionRecord",
    "KnowledgeEvolution",
    "create_evolution",
]