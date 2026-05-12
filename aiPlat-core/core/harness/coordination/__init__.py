"""
Coordination Module

Multi-agent coordination via Patterns (primary) and Convergence Detectors.
Coordinator classes (SimpleCoordinator, AdaptiveCoordinator, HierarchicalCoordinator)
have been removed as dead code — use create_pattern() instead.
"""

from .patterns import (
    CoordinationContext,
    CoordinationResult,
    ICoordinationPattern,
    PipelinePattern,
    FanOutFanInPattern,
    ExpertPoolPattern,
    ProducerReviewerPattern,
    SupervisorPattern,
    create_pattern,
)
from .detector.convergence import (
    IConvergenceDetector,
    ConvergenceResult,
    ExactMatchDetector,
    SimilarityDetector,
    SemanticSimilarityDetector,
    VotingDetector,
    create_detector,
)

__all__ = [
    "CoordinationContext",
    "CoordinationResult",
    "ICoordinationPattern",
    "PipelinePattern",
    "FanOutFanInPattern",
    "ExpertPoolPattern",
    "ProducerReviewerPattern",
    "SupervisorPattern",
    "create_pattern",
    "IConvergenceDetector",
    "ConvergenceResult",
    "ExactMatchDetector",
    "SimilarityDetector",
    "SemanticSimilarityDetector",
    "VotingDetector",
    "create_detector",
]