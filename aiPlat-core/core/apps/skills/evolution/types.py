"""
Skill Evolution Types

Defines types for Skill evolution system.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class EvolutionType(Enum):
    """Evolution type"""
    FIX = "fix"           # Fix errors in existing skill
    DERIVED = "derived"   # Create new branch from existing skill
    CAPTURED = "captured" # Capture new skill from successful execution


class TriggerType(Enum):
    """Evolution trigger type"""
    POST_EXEC = "post_exec"           # After task execution
    TOOL_DEGRADATION = "tool_degradation"  # Tool success rate drop
    METRIC = "metric"                 # Metric threshold reached


class TriggerStatus(Enum):
    """Trigger status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class EvolutionTrigger:
    """Evolution trigger record"""
    id: str
    skill_id: str
    trigger_type: TriggerType
    status: TriggerStatus = TriggerStatus.PENDING
    suggestion: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillVersion:
    """Skill version with lineage"""
    id: str
    skill_id: str
    version: str
    parent_version: Optional[str] = None
    evolution_type: Optional[EvolutionType] = None
    trigger: str = ""
    content_hash: str = ""
    diff: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvolutionSuggestion:
    """Evolution suggestion from analysis"""
    suggestion_type: EvolutionType
    reason: str
    target_skill: str
    changes: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass
class EvolutionResult:
    """Result of evolution operation"""
    success: bool
    new_version: Optional[SkillVersion] = None
    error: Optional[str] = None
    reverted: bool = False


# Anti-infinite-evolution config
@dataclass
class EvolutionConfig:
    """Evolution configuration"""
    cooldown_hours: int = 24
    max_versions_per_skill: int = 50
    require_approval_for_destructive: bool = True
    auto_rollback_on_degradation: bool = True
    degradation_threshold: float = 0.1  # 10% performance drop


__all__ = [
    "EvolutionType",
    "TriggerType",
    "TriggerStatus",
    "EvolutionTrigger",
    "SkillVersion",
    "EvolutionSuggestion",
    "EvolutionResult",
    "EvolutionConfig"
]