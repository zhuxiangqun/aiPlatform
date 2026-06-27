"""
Knowledge Gap Detector — identify missing knowledge from query patterns.

Analyzes query logs against the ontology and graph to detect three gap types:
  no_entity:      query doesn't match any ontology class (OOV)
  no_instance:    class matched but no instances found in graph
  low_relevance:  instances found but confidence/relevance too low

This is the first step from L4 (passive response) toward L5 (active perception).
"""

from __future__ import annotations
import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import Counter


@dataclass
class KnowledgeGap:
    query: str
    frequency: int
    gap_type: str  # "no_entity" | "no_instance" | "low_relevance"
    matched_classes: List[str] = field(default_factory=list)
    confidence: float = 0.0
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "frequency": self.frequency,
            "gap_type": self.gap_type,
            "matched_classes": self.matched_classes,
            "confidence": self.confidence,
            "suggestion": self.suggestion,
        }


def detect_knowledge_gaps(
    queries: List[str],
    *,
    domain_id: str = "ai-knowledge",
    min_frequency: int = 2,
    max_gaps: int = 20,
) -> Dict[str, Any]:
    """Detect knowledge gaps from a list of query strings.

    Args:
        queries: list of user query strings
        domain_id: ontology domain to check against
        min_frequency: minimum occurrences to flag as a gap
        max_gaps: maximum gaps to return

    Returns:
        { gaps: [KnowledgeGap, ...], summary: { total, by_type } }
    """
    # Count query frequency
    counter = Counter(queries)
    frequent = [(q, c) for q, c in counter.most_common(max_gaps * 3) if c >= min_frequency]

    # Load ontology mapper
    try:
        from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology
    except ImportError:
        return {"gaps": [], "summary": {"total": 0, "by_type": {}}}

    # Load graph for instance check
    graph = None
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    gaps: List[KnowledgeGap] = []

    for query, freq in frequent:
        try:
            mapping = map_query_to_ontology(query)
        except Exception:
            mapping = None

        matched = (mapping.get("matched_classes") or []) if mapping else []
        best_confidence = matched[0].get("score", 0) if matched else 0

        # Gap type 1: no entity — query doesn't match any class
        if not matched or best_confidence < 0.5:
            gaps.append(KnowledgeGap(
                query=query,
                frequency=freq,
                gap_type="no_entity",
                confidence=best_confidence,
                suggestion="建议新增本体类或扩展关键词覆盖",
            ))
            continue

        # Gap type 2: no instance — class exists but no graph nodes
        matched_labels = [m.get("label", "") for m in matched[:3]]
        has_instance = False
        if graph:
            for label in matched_labels:
                node = graph.find_by_name(label)
                if node:
                    has_instance = True
                    break

        if not has_instance and graph is not None:
            gaps.append(KnowledgeGap(
                query=query,
                frequency=freq,
                gap_type="no_instance",
                matched_classes=matched_labels,
                confidence=best_confidence,
                suggestion=f"类 '{matched_labels[0]}' 存在但无实例。建议上传相关文档或手动创建页面。",
            ))
            continue

        # Gap type 3: low relevance — class+instance exist but confidence is marginal
        if best_confidence < 0.7:
            gaps.append(KnowledgeGap(
                query=query,
                frequency=freq,
                gap_type="low_relevance",
                matched_classes=matched_labels,
                confidence=best_confidence,
                suggestion="检索置信度偏低，建议优化类关键词或同义词覆盖",
            ))

        if len(gaps) >= max_gaps:
            break

    by_type = Counter(g.gap_type for g in gaps)
    return {
        "gaps": [g.to_dict() for g in gaps],
        "summary": {
            "total": len(gaps),
            "by_type": dict(by_type),
            "queries_analyzed": len(frequent),
            "min_frequency": min_frequency,
        },
    }
