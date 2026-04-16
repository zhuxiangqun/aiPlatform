"""
Phase 6: learning artifact types (versioned, traceable, rollbackable).

Important:
- These types must be JSON-serializable for storage in ExecutionStore.
- Artifacts are side-effect free metadata; applying an artifact (publishing) is a separate step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
import time


class LearningArtifactKind(str, Enum):
    EVALUATION_REPORT = "evaluation_report"
    REGRESSION_REPORT = "regression_report"
    FEEDBACK_SUMMARY = "feedback_summary"
    SKILL_EVOLUTION = "skill_evolution"
    SKILL_ROLLBACK = "skill_rollback"
    RELEASE_CANDIDATE = "release_candidate"
    PROMPT_REVISION = "prompt_revision"
    POLICY_REVISION = "policy_revision"


class LearningArtifactStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ROLLED_BACK = "rolled_back"


@dataclass
class LearningArtifact:
    artifact_id: str
    kind: LearningArtifactKind
    target_type: str  # agent|skill|prompt|policy
    target_id: str
    version: str
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT

    # Traceability
    trace_id: Optional[str] = None
    run_id: Optional[str] = None

    # Payload
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())

    def to_record(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind.value,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "version": self.version,
            "status": self.status.value,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "payload": self.payload or {},
            "metadata": self.metadata or {},
            "created_at": self.created_at,
        }
