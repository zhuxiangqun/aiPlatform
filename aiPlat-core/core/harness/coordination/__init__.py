"""
Coordination Module
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
from .coordinators.agent import (
    SimpleCoordinator,
    AdaptiveCoordinator,
    HierarchicalCoordinator,
    create_coordinator,
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
    "SimpleCoordinator",
    "AdaptiveCoordinator",
    "HierarchicalCoordinator",
    "create_coordinator",
    "IConvergenceDetector",
    "ConvergenceResult",
    "ExactMatchDetector",
    "SimilarityDetector",
    "SemanticSimilarityDetector",
    "VotingDetector",
    "create_detector",
]