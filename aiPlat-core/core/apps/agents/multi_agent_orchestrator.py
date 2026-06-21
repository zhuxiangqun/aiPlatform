"""
Multi-Agent Orchestrator — lightweight coordination between specialized agents.

Routes complex queries through multiple agent types and merges results.
Supports: ontology classification → graph traversal → knowledge retrieval chain.

Usage:
  orchestrator = MultiAgentOrchestrator()
  result = await orchestrator.execute(query, context)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class MultiAgentOrchestrator:
    """Lightweight multi-agent coordinator for L5+ readiness."""

    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._routing_rules: List[Dict[str, Any]] = [
            {
                "intent": "knowledge_query",
                "keywords": ["是什么", "如何", "原理", "区别", "比较", "原因", "为什么"],
                "agents": ["ontology_mapper", "graph_traversal", "knowledge_chat"],
            },
            {
                "intent": "fact_lookup",
                "keywords": ["谁", "哪个", "多少", "什么时候", "在哪里"],
                "agents": ["knowledge_chat", "graph_traversal"],
            },
            {
                "intent": "default",
                "keywords": [],
                "agents": ["knowledge_chat"],
            },
        ]

    def route(self, query: str) -> List[str]:
        """Determine which agents to invoke based on query keywords."""
        q = query.lower()
        for rule in self._routing_rules:
            if rule["intent"] == "default":
                continue
            if any(kw in q for kw in rule["keywords"]):
                return rule["agents"]
        return ["knowledge_chat"]

    async def execute_pipeline(
        self,
        query: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        domain_id: str = "ai-knowledge",
    ) -> Dict[str, Any]:
        """Execute a multi-agent pipeline and merge results.

        Pipeline: ontology_mapper → graph_traversal → knowledge_chat
        """
        pipeline_results: Dict[str, Any] = {"query": query}

        # Stage 1: Ontology mapping (classify the question)
        try:
            from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology
            mapping = map_query_to_ontology(query)
            pipeline_results["ontology_mapping"] = mapping
        except Exception:
            pipeline_results["ontology_mapping"] = None

        # Stage 2: Graph traversal (find related entities)
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            from core.harness.ontology_engine.graph_traversal import traverse_multi
            graph = GraphIndex.load(domain_id)
            if len(graph) > 0:
                matched_labels = []
                if pipeline_results.get("ontology_mapping"):
                    for mc in (pipeline_results["ontology_mapping"].get("matched_classes") or [])[:2]:
                        label = mc.get("label", "")
                        if label:
                            node = graph.find_by_name(label)
                            if node:
                                matched_labels.append(node.entity_id)
                if matched_labels:
                    traversal = traverse_multi(matched_labels, graph, max_hops=2)
                    pipeline_results["graph_traversal"] = {
                        "terminals": traversal.terminal_entities,
                        "ranked": traversal.ranked_terminals,
                        "paths_found": traversal.stats.get("paths_found", 0),
                    }
        except Exception:
            pipeline_results["graph_traversal"] = None

        # Stage 3: Knowledge retrieval + answer generation
        # (This is handled by MaterialsChatAgent — just report results)
        pipeline_results["agents_invoked"] = self.route(query)

        # Merge: collect terminal entity names to enrich context
        traversal = pipeline_results.get("graph_traversal")
        if traversal and traversal.get("terminals"):
            pipeline_results["enriched_context"] = [
                t.get("entity_name", "") for t in traversal["terminals"][:5]
            ]

        return pipeline_results


# Singleton
_orchestrator: Optional[MultiAgentOrchestrator] = None


def get_orchestrator() -> MultiAgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MultiAgentOrchestrator()
    return _orchestrator
