"""
Convergence Detector Module

Detects when multi-agent results have converged.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Dict
# NOTE: numpy is intentionally not used here. Avoid importing heavy optional deps.


@dataclass
class ConvergenceResult:
    """Convergence detection result"""
    converged: bool
    similarity_score: float
    method: str
    details: Dict[str, Any] = field(default_factory=dict)


class IConvergenceDetector(ABC):
    """
    Convergence detector interface
    """

    @abstractmethod
    def detect(self, results: List[Any]) -> ConvergenceResult:
        """Detect convergence in results"""
        pass


class ExactMatchDetector(IConvergenceDetector):
    """
    Exact Match Detector
    
    Results must be identical to be considered converged.
    """

    def __init__(self, threshold: float = 1.0):
        self._threshold = threshold

    def detect(self, results: List[Any]) -> ConvergenceResult:
        """Detect exact match convergence"""
        if len(results) < 2:
            return ConvergenceResult(
                converged=False,
                similarity_score=0.0,
                method="exact_match"
            )
        
        # Convert to strings
        str_results = [str(r) for r in results]
        
        # Check if all are the same
        unique = set(str_results)
        
        if len(unique) == 1:
            return ConvergenceResult(
                converged=True,
                similarity_score=1.0,
                method="exact_match",
                details={"matches": len(results)}
            )
        
        return ConvergenceResult(
            converged=False,
            similarity_score=0.0,
            method="exact_match",
            details={"unique_count": len(unique)}
        )


class SimilarityDetector(IConvergenceDetector):
    """
    Similarity-based Detector
    
    Uses text similarity to detect convergence.
    """

    def __init__(self, threshold: float = 0.8):
        self._threshold = threshold

    def detect(self, results: List[Any]) -> ConvergenceResult:
        """Detect similarity-based convergence"""
        if len(results) < 2:
            return ConvergenceResult(
                converged=False,
                similarity_score=0.0,
                method="similarity"
            )
        
        str_results = [str(r) for r in results]
        
        # Calculate pairwise similarity
        similarities = []
        
        for i in range(len(str_results)):
            for j in range(i + 1, len(str_results)):
                sim = self._calculate_similarity(str_results[i], str_results[j])
                similarities.append(sim)
        
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        
        return ConvergenceResult(
            converged=avg_similarity >= self._threshold,
            similarity_score=avg_similarity,
            method="similarity",
            details={"threshold": self._threshold}
        )

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity (simple word overlap)"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)


class SemanticSimilarityDetector(IConvergenceDetector):
    """
    Semantic Similarity Detector
    
    Uses embeddings to detect semantic convergence.
    """

    def __init__(self, threshold: float = 0.85, model: Any = None):
        self._threshold = threshold
        self._model = model

    def detect(self, results: List[Any]) -> ConvergenceResult:
        """Detect semantic convergence"""
        if not self._model:
            return ConvergenceResult(
                converged=False,
                similarity_score=0.0,
                method="semantic",
                details={"error": "No embedding model"}
            )
        
        # Generate embeddings
        embeddings = []
        
        for result in results:
            try:
                # Use model to get embedding
                embedding = self._model.embed(str(result))
                embeddings.append(embedding)
            except Exception:
                return ConvergenceResult(
                    converged=False,
                    similarity_score=0.0,
                    method="semantic",
                    details={"error": "Embedding failed"}
                )
        
        # Calculate cosine similarity
        similarities = []
        
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = self._cosine_similarity(embeddings[i], embeddings[j])
                similarities.append(sim)
        
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        
        return ConvergenceResult(
            converged=avg_similarity >= self._threshold,
            similarity_score=avg_similarity,
            method="semantic",
            details={"threshold": self._threshold}
        )

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity"""
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot / (norm1 * norm2)


class VotingDetector(IConvergenceDetector):
    """
    Voting-based Detector
    
    Uses voting to determine convergence.
    """

    def __init__(self, min_votes: int = 2):
        self._min_votes = min_votes

    def detect(self, results: List[Any]) -> ConvergenceResult:
        """Detect convergence through voting"""
        if len(results) < 2:
            return ConvergenceResult(
                converged=False,
                similarity_score=0.0,
                method="voting"
            )
        
        str_results = [str(r) for r in results]
        
        # Count votes
        from collections import Counter
        votes = Counter(str_results)
        
        most_common_count = votes.most_common(1)[0][1]
        vote_ratio = most_common_count / len(results)
        
        return ConvergenceResult(
            converged=most_common_count >= self._min_votes,
            similarity_score=vote_ratio,
            method="voting",
            details={
                "votes": dict(votes),
                "threshold": self._min_votes
            }
        )


def create_detector(
    detector_type: str = "exact",
    threshold: float = 0.8,
    **kwargs
) -> IConvergenceDetector:
    """Factory function to create convergence detector"""
    detectors = {
        "exact": ExactMatchDetector,
        "similarity": SimilarityDetector,
        "semantic": SemanticSimilarityDetector,
        "voting": VotingDetector,
    }
    
    if detector_type not in detectors:
        raise ValueError(f"Unknown detector type: {detector_type}")
    
    return detectors[detector_type](threshold=threshold, **kwargs)
