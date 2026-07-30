"""
Evaluation policy schemas — structured config for automated evaluation.

Policies define what, when, and how to evaluate AI outputs.
They are stored as LearningArtifacts (kind=evaluation_policy) via LearningManager.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvalTrigger(str, Enum):
    ON_DEPLOY = "on_deploy"
    ON_SCHEDULE = "on_schedule"
    ON_REQUEST = "on_request"
    ON_FEEDBACK_THRESHOLD = "on_feedback_threshold"


class EvalMetric(str, Enum):
    ACCURACY = "accuracy"
    FAITHFULNESS = "faithfulness"
    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"
    LATENCY = "latency"
    COST = "cost"
    CONSISTENCY = "consistency"


@dataclass
class EvalPolicy:
    """Evaluation policy — when and how to evaluate."""
    policy_id: str
    name: str = ""
    description: str = ""
    version: str = "1.0.0"

    # What to evaluate
    target_type: str = "agent"  # agent | skill | prompt
    target_ids: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=lambda: [EvalMetric.ACCURACY, EvalMetric.FAITHFULNESS])

    # When to evaluate
    triggers: List[str] = field(default_factory=lambda: [EvalTrigger.ON_DEPLOY])
    schedule_cron: str = ""

    # Thresholds
    pass_threshold: float = 0.70
    warn_threshold: float = 0.60
    max_retries: int = 3

    # Actions on failure
    on_fail: str = "warn"  # warn | block | rollback
    notify_channels: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "target_type": self.target_type,
            "target_ids": self.target_ids,
            "metrics": self.metrics,
            "triggers": self.triggers,
            "schedule_cron": self.schedule_cron,
            "pass_threshold": self.pass_threshold,
            "warn_threshold": self.warn_threshold,
            "max_retries": self.max_retries,
            "on_fail": self.on_fail,
            "notify_channels": self.notify_channels,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalPolicy":
        return cls(
            policy_id=data.get("policy_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            target_type=data.get("target_type", "agent"),
            target_ids=data.get("target_ids", []),
            metrics=data.get("metrics", []),
            triggers=data.get("triggers", []),
            schedule_cron=data.get("schedule_cron", ""),
            pass_threshold=data.get("pass_threshold", 0.70),
            warn_threshold=data.get("warn_threshold", 0.60),
            max_retries=data.get("max_retries", 3),
            on_fail=data.get("on_fail", "warn"),
            notify_channels=data.get("notify_channels", []),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def default_for(cls, target_type: str, target_id: str) -> "EvalPolicy":
        return cls(
            policy_id=f"{target_type}:{target_id}",
            name=f"Default evaluation for {target_type} {target_id}",
            target_type=target_type,
            target_ids=[target_id],
        )
