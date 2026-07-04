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

        # Stage 1+2+3: Unified ontology→graph traversal (shared pipeline)
        try:
            from core.harness.knowledge.orchestrated_retrieval import traverse_ontology_graph
            trav = traverse_ontology_graph(query, domain_id=domain_id, max_hops=2)
            pipeline_results["ontology_mapping"] = trav["ontology_mapping"]
            if trav["success"]:
                pipeline_results["graph_traversal"] = {
                    "terminals": trav["terminal_entities"],
                    "ranked": trav["terminal_entities"],
                    "paths_found": len(trav["traversal_paths"]),
                }
        except Exception:
            pipeline_results["ontology_mapping"] = None
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
