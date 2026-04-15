"""
Tool Recaller Module (TokMem Hybrid Recall)

Provides hybrid tool recall combining Token-based and RAG-based retrieval.
Includes TokenRecaller, RAGRecaller, ToolRecaller, and NeuralEnhancer.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum


class RecallSource(Enum):
    TOKEN = "token"
    RAG = "rag"
    MIXED = "mixed"


@dataclass
class RecallResult:
    tool_name: str
    score: float
    source: RecallSource
    token_score: float = 0.0
    rag_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class TokenRecaller:
    """
    Token-based Tool Recaller

    Recalls tools using keyword matching against tool names and descriptions.
    """

    def __init__(self):
        self._index: Dict[str, Set[str]] = {}
        self._tool_descriptions: Dict[str, str] = {}

    def index_tool(self, tool_name: str, description: str, keywords: Optional[List[str]] = None) -> None:
        """Index a tool for token-based recall"""
        self._tool_descriptions[tool_name] = description.lower()
        tokens = set()
        if keywords:
            tokens.update(kw.lower() for kw in keywords)
        tokens.update(tool_name.lower().split("_"))
        tokens.update(description.lower().split())
        self._index[tool_name] = tokens

    def remove_tool(self, tool_name: str) -> None:
        """Remove a tool from the index"""
        self._index.pop(tool_name, None)
        self._tool_descriptions.pop(tool_name, None)

    def recall(self, query: str, top_k: int = 5) -> List[RecallResult]:
        """Recall tools based on keyword matching"""
        query_tokens = set(query.lower().split())
        results: List[RecallResult] = []

        for tool_name, tool_tokens in self._index.items():
            intersection = query_tokens & tool_tokens
            if not intersection:
                continue
            union = query_tokens | tool_tokens
            score = len(intersection) / len(union) if union else 0.0
            results.append(RecallResult(
                tool_name=tool_name,
                score=score,
                source=RecallSource.TOKEN,
                token_score=score,
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    @property
    def tool_count(self) -> int:
        return len(self._index)


class RAGRecaller:
    """
    RAG-based Tool Recaller

    Recalls tools using semantic similarity (simulated with TF-IDF-like scoring).
    In production, this would use vector embeddings.
    """

    def __init__(self):
        self._tool_texts: Dict[str, str] = {}
        self._tool_vectors: Dict[str, Dict[str, float]] = {}

    def index_tool(self, tool_name: str, description: str) -> None:
        """Index a tool for RAG-based recall"""
        self._tool_texts[tool_name] = description
        self._tool_vectors[tool_name] = self._compute_vector(description)

    def remove_tool(self, tool_name: str) -> None:
        """Remove a tool from the index"""
        self._tool_texts.pop(tool_name, None)
        self._tool_vectors.pop(tool_name, None)

    def _compute_vector(self, text: str) -> Dict[str, float]:
        """Compute a simple term frequency vector (simulated embedding)"""
        words = text.lower().split()
        vector: Dict[str, float] = {}
        total = len(words)
        for word in words:
            vector[word] = vector.get(word, 0.0) + 1.0
        if total > 0:
            for word in vector:
                vector[word] /= total
        return vector

    def _cosine_similarity(self, vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        """Compute cosine similarity between two vectors"""
        common_keys = set(vec_a.keys()) & set(vec_b.keys())
        if not common_keys:
            return 0.0
        dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)
        norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def recall(self, query: str, top_k: int = 5) -> List[RecallResult]:
        """Recall tools using semantic similarity"""
        query_vector = self._compute_vector(query)
        results: List[RecallResult] = []

        for tool_name, tool_vector in self._tool_vectors.items():
            score = self._cosine_similarity(query_vector, tool_vector)
            if score > 0:
                results.append(RecallResult(
                    tool_name=tool_name,
                    score=score,
                    source=RecallSource.RAG,
                    rag_score=score,
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    @property
    def tool_count(self) -> int:
        return len(self._tool_texts)


class NeuralEnhancer:
    """
    Neural Network Feature Enhancer

    Enhances recall scores using a simple three-layer network.
    In production, this would use a trained neural model.
    """

    def __init__(self, hidden_size: int = 16):
        self._hidden_size = hidden_size
        self._weights_initialized = False

    def enhance(
        self,
        token_score: float,
        rag_score: float,
        weight_token: float = 0.4,
        weight_rag: float = 0.6
    ) -> float:
        """Enhance recall scores using feature combination"""
        product = token_score * rag_score
        total_sum = token_score + rag_score
        difference = abs(token_score - rag_score)
        square_sum = token_score ** 2 + rag_score ** 2
        geometric_mean = math.sqrt(max(token_score, 0.001) * max(rag_score, 0.001))

        enhanced = (
            weight_token * token_score +
            weight_rag * rag_score +
            0.1 * product +
            0.05 * difference +
            0.05 * square_sum +
            0.1 * geometric_mean
        )

        return min(max(enhanced, 0.0), 1.0)


class ToolRecaller:
    """
    Hybrid Tool Recaller (TokMem)

    Combines Token-based and RAG-based recall with configurable weights.
    Optionally uses NeuralEnhancer for score refinement.
    """

    def __init__(
        self,
        weight_token: float = 0.4,
        weight_rag: float = 0.6,
        use_neural_enhancer: bool = False
    ):
        self.weight_token = weight_token
        self.weight_rag = weight_rag
        self.token_recaller = TokenRecaller()
        self.rag_recaller = RAGRecaller()
        self.neural_enhancer = NeuralEnhancer() if use_neural_enhancer else None

    def index_tool(
        self,
        tool_name: str,
        description: str,
        keywords: Optional[List[str]] = None
    ) -> None:
        """Index a tool for hybrid recall"""
        self.token_recaller.index_tool(tool_name, description, keywords)
        self.rag_recaller.index_tool(tool_name, description)

    def remove_tool(self, tool_name: str) -> None:
        """Remove a tool from the index"""
        self.token_recaller.remove_tool(tool_name)
        self.rag_recaller.remove_tool(tool_name)

    def recall(self, query: str, top_k: int = 5) -> List[RecallResult]:
        """
        Recall tools using hybrid approach.

        Combines token-based and RAG-based scores with configurable weights.
        Optionally applies neural enhancement.

        Args:
            query: Search query
            top_k: Number of top results to return

        Returns:
            List of RecallResult sorted by score
        """
        token_results = self.token_recaller.recall(query, top_k=top_k * 2)
        rag_results = self.rag_recaller.recall(query, top_k=top_k * 2)

        all_tools: Set[str] = set()
        for r in token_results:
            all_tools.add(r.tool_name)
        for r in rag_results:
            all_tools.add(r.tool_name)

        token_map = {r.tool_name: r.token_score for r in token_results}
        rag_map = {r.tool_name: r.rag_score for r in rag_results}

        results: List[RecallResult] = []
        for tool_name in all_tools:
            token_score = token_map.get(tool_name, 0.0)
            rag_score = rag_map.get(tool_name, 0.0)

            if self.neural_enhancer:
                mixed_score = self.neural_enhancer.enhance(token_score, rag_score, self.weight_token, self.weight_rag)
            else:
                mixed_score = self.weight_token * token_score + self.weight_rag * rag_score

            results.append(RecallResult(
                tool_name=tool_name,
                score=mixed_score,
                source=RecallSource.MIXED if (token_score > 0 and rag_score > 0) else (RecallSource.TOKEN if token_score > 0 else RecallSource.RAG),
                token_score=token_score,
                rag_score=rag_score,
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    @property
    def tool_count(self) -> int:
        return self.token_recaller.tool_count


# Global tool recaller
_global_recaller: Optional[ToolRecaller] = None


def get_tool_recaller() -> ToolRecaller:
    """Get global tool recaller"""
    global _global_recaller
    if _global_recaller is None:
        _global_recaller = ToolRecaller()
    return _global_recaller