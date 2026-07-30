"""
Learning loop (Phase 6 — fully implemented, 2026-07-29).

Powers "evaluation → feedback → evolution" controlled improvement.

Capabilities:
- Benchmark evaluation (LearningManager.run_benchmark)
- Feedback aggregation (LearningManager.aggregate_feedback)  
- Evolution proposals (LearningManager.propose_evolution)
- Artifact lifecycle: draft → published → rolled_back
- Auto-rollback on regression (autorollback)
- Release candidate management (release)
- Artifact application (apply)
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

from .autorollback import auto_rollback_regression, cleanup_rollback_approvals
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
    "auto_rollback_regression",
    "cleanup_rollback_approvals",
    "build_release_candidate",
    "LearningApplier",
    "ActiveRelease",
]
