"""
Learning loop (Phase 6 - placeholder).

This package defines the versioned artifacts and persistence interfaces that power
"evaluation → feedback → evolution" controlled improvement.

Phase 6 scope in this repo (current):
- Provide types + persistence hooks
- Do NOT change online execution behavior unless explicitly enabled
"""

from .types import (
    LearningArtifact,
    LearningArtifactKind,
    LearningArtifactStatus,
)
from .manager import LearningManager
from .pipeline import (
    artifact_from_benchmark_result,
    artifact_from_feedback_summary,
    artifact_from_skill_evolution,
    artifact_from_online_run_summary,
    summarize_syscall_events,
    artifact_from_regression_result,
    artifact_from_skill_version,
    artifact_from_skill_rollback,
    artifact_from_prompt_revision,
    artifact_from_regression_decision,
)
from .release import build_release_candidate
from .apply import LearningApplier, ActiveRelease

__all__ = [
    "LearningArtifact",
    "LearningArtifactKind",
    "LearningArtifactStatus",
    "LearningManager",
    "artifact_from_benchmark_result",
    "artifact_from_feedback_summary",
    "artifact_from_skill_evolution",
    "artifact_from_online_run_summary",
    "summarize_syscall_events",
    "artifact_from_regression_result",
    "artifact_from_skill_version",
    "artifact_from_skill_rollback",
    "artifact_from_prompt_revision",
    "artifact_from_regression_decision",
    "build_release_candidate",
    "LearningApplier",
    "ActiveRelease",
]
