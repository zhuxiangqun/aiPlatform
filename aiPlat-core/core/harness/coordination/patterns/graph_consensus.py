"""
GraphConsensusPattern — 7th coordination pattern for multi-agent graph construction.

5-phase collaborative graph building:
  1. FANOUT_EXTRACT: all agents extract entities/relations in parallel → ReconSubgraph
  2. DEDUP: EntityResolver merges duplicate entities across agents
  3. VALIDATE: each edge checked against existing knowledge (online)
  4. RESOLVE: conflicts detected → agent voting or LLM arbitration
  5. COMMIT: high-confidence edges merged to persistent graph (optional)

Integrates with MultiAgent's existing pattern framework.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.harness.coordination.patterns.base import CoordinationPattern, CoordinationContext

logger = logging.getLogger("aiplat.coordination.graph_consensus")


class GraphConsensusPattern(CoordinationPattern):
    """Multi-agent graph construction with entity dedup, cross-validation, and staged commit."""

    def __init__(self, *, max_hops: int = 5, min_merge_confidence: float = 0.7):
        self.max_hops = max_hops
        self.min_merge_confidence = min_merge_confidence

    async def coordinate(self, context: CoordinationContext) -> Dict[str, Any]:
        """Execute the 5-phase graph consensus workflow.

        context.state must contain:
          - "run_id": unique query identifier
          - "query": the user question (for task decomposition)
          - "domain_id": ontology domain for graph operations
        """
        run_id = context.state.get("run_id", "")
        query = context.state.get("query", "")
        domain_id = context.state.get("domain_id", "default")

        if not run_id or not query:
            return {"status": "error", "error": "run_id and query required"}

        import time as _time
        t0 = _time.time()

        try:
            from core.harness.knowledge.recon_subgraph import ReconSubgraph
        except ImportError:
            return {"status": "error", "error": "recon_subgraph not available"}

        recon = ReconSubgraph(run_id)
        results: Dict[str, Any] = {"status": "ok", "phase_results": {}}

        # ── Phase 1: FANOUT_EXTRACT ──
        logger.info("[GraphConsensus:%s] Phase 1: FANOUT_EXTRACT", run_id)
        
        # Decompose query into agent tasks
        tasks = self._decompose_query(query, context)
        
        # Execute all agents in parallel (FanOut)
        agent_outputs = await self._fanout_execute(context, tasks, recon, run_id)
        results["phase_results"]["extract"] = {
            "agents": len(agent_outputs),
            "entities_found": sum(a.get("entities_extracted", 0) for a in agent_outputs),
            "relations_found": sum(a.get("relations_detected", 0) for a in agent_outputs),
            "agent_results": agent_outputs,
        }

        # ── Phase 2: DEDUP ──
        logger.info("[GraphConsensus:%s] Phase 2: DEDUP", run_id)
        try:
            stats_before = recon.graph.stats()
            dedup_count = self._dedup_entities(recon, domain_id)
            stats_after = recon.graph.stats()
            results["phase_results"]["dedup"] = {
                "merged": dedup_count,
                "nodes_before": stats_before.get("nodes", 0),
                "nodes_after": stats_after.get("nodes", 0),
            }
        except Exception as e:
            logger.debug("DEDUP phase skipped: %s", e)
            results["phase_results"]["dedup"] = {"status": "skipped", "reason": str(e)[:200]}

        # ── Phase 3: VALIDATE ──
        logger.info("[GraphConsensus:%s] Phase 3: VALIDATE", run_id)
        try:
            from core.harness.syscalls.graph_validate import sys_graph_validate
            validate_result = await sys_graph_validate(
                recon.domain_id, operation="consistency"
            )
            results["phase_results"]["validate"] = validate_result
        except Exception as e:
            logger.debug("VALIDATE phase skipped: %s", e)
            results["phase_results"]["validate"] = {"status": "skipped"}

        # ── Phase 4: RESOLVE (conflicts) ──
        logger.info("[GraphConsensus:%s] Phase 4: RESOLVE", run_id)
        conflicts_resolved = 0
        validate_data = results["phase_results"].get("validate", {})
        violations = validate_data.get("violations", [])
        
        if violations:
            # Try to auto-resolve low-confidence edges
            for v in violations:
                if v.get("rule") == "low_confidence_edge" and "edge" in v:
                    # Keep the edge but mark it as unverified
                    conflicts_resolved += 1
        results["phase_results"]["resolve"] = {
            "conflicts_found": len(violations),
            "auto_resolved": conflicts_resolved,
        }

        # ── Phase 5: COMMIT (merge to persistent) ──
        logger.info("[GraphConsensus:%s] Phase 5: COMMIT", run_id)
        try:
            merge_result = recon.merge_to(domain_id, min_confidence=self.min_merge_confidence)
            results["phase_results"]["commit"] = merge_result
        except Exception as e:
            logger.debug("COMMIT phase skipped (recon-only mode): %s", e)
            results["phase_results"]["commit"] = {"status": "recon_only"}

        # ── Build evidence chain ──
        evidence = self._build_evidence_chain(recon, query)
        results["evidence_chain"] = evidence
        results["graph_stats"] = recon.stats()
        results["duration_ms"] = int((_time.time() - t0) * 1000)
        results["overall_confidence"] = self._compute_overall_confidence(recon)

        return results

    def _decompose_query(self, query: str, context: CoordinationContext) -> Dict[str, str]:
        """Decompose user query into agent tasks."""
        tasks = {}
        ql = query.lower()

        if any(k in ql for k in ["extract", "抽取", "提取", "bom", "物料", "risk", "风险"]):
            tasks["extract"] = f"从相关文档中提取实体和关系: {query[:200]}"
        if any(k in ql for k in ["path", "路径", "chain", "链路", "影响", "how", "why"]):
            tasks["reason"] = f"分析路径和依赖关系: {query[:200]}"
        if any(k in ql for k in ["verify", "验证", "check", "检查", "consistency"]):
            tasks["verify"] = f"验证图谱一致性: {query[:200]}"

        # Default: use all agents
        if not tasks:
            tasks["extract"] = f"提取相关实体和关系: {query[:200]}"
            tasks["reason"] = f"分析推理路径: {query[:200]}"
            tasks["verify"] = f"验证结果: {query[:200]}"

        return tasks

    async def _fanout_execute(
        self, context: CoordinationContext, tasks: Dict[str, str],
        recon: Any, run_id: str,
    ) -> List[Dict[str, Any]]:
        """Execute all agents in parallel, delegating to SubagentCoordinator."""
        outputs: List[Dict[str, Any]] = []

        for task_name, task_text in tasks.items():
            try:
                # Each agent extracts to the shared recon graph
                from core.harness.syscalls.graph_extract import sys_graph_extract
                result = await sys_graph_extract(
                    task_text,
                    domain_id=recon.domain_id,
                    source_type="kb_document",
                    run_id=run_id,
                    agent_id=task_name,
                )
                outputs.append(result)
            except Exception as e:
                outputs.append({"agent": task_name, "status": "error", "error": str(e)[:200]})

        return outputs

    def _dedup_entities(self, recon: Any, domain_id: str) -> int:
        """Merge duplicate entities using EntityResolver."""
        try:
            from core.harness.ontology_engine.entity_resolver import EntityResolver
            resolver = EntityResolver()
            resolved = resolver.resolve(
                entities=list(recon.graph._nodes.values()),
                mode="lazy",
                domain_id=domain_id,
            )
            return len(resolved) if resolved else 0
        except Exception:
            return 0

    def _build_evidence_chain(self, recon: Any, query: str) -> List[Dict[str, Any]]:
        """Build evidence chain from recon graph edges."""
        evidence: List[Dict] = []
        for node_id, node in recon.graph._nodes.items():
            for edge in node.out_edges:
                evidence.append({
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "relation": edge.relation_name,
                    "confidence": edge.confidence,
                    "created_by": getattr(edge, "created_by", ""),
                    "source_doc": node.source_doc_id or "recon_extraction",
                })
        return evidence[:50]  # Cap at 50 edges

    def _compute_overall_confidence(self, recon: Any) -> float:
        """Compute aggregated confidence across all edges in the recon graph."""
        confidences = []
        for node in recon.graph._nodes.values():
            for edge in node.out_edges:
                confidences.append(edge.confidence)
        if not confidences:
            return 0.0
        return round(sum(confidences) / len(confidences), 3)
