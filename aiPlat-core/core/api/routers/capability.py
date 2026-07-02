"""
Capability Graph & Health API — pure graph + analysis endpoints.

Endpoints:
  GET /capability-graph   → nodes + edges (factual, zero analysis)
  GET /capability-health  → health score, issues, top hubs, blast

Graph/Analysis separation: two endpoints, one source of truth.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from core.harness.knowledge.capability_graph import build_capability_graph
from core.harness.knowledge.capability_health import capability_health_report

router = APIRouter()


@router.get("/capability-graph", response_model=Dict[str, Any])
async def get_capability_graph() -> Dict[str, Any]:
    u"""Return the pure AI capability graph (nodes + edges, zero analysis).

    Nodes: agent, skill, tool, mcp_server, workflow, syscall
    Edges: requires, uses, provides, maps_to

    This is a factual snapshot of what exists — no health scores, no recommendations.
    """
    g = build_capability_graph()
    return {
        "nodes": list(g.nodes.values()),
        "edges": g.edges,
    }


@router.get("/capability-health", response_model=Dict[str, Any])
async def get_capability_health() -> Dict[str, Any]:
    u"""Return the AI capability health analysis.

    Reads the capability graph and produces:
      - score / grade (0-100)
      - signals (node/edge counts by type)
      - issues (unused skills, orphan agents, unresolved references)
      - top_hubs (most connected nodes)
      - top_blast (largest impact radius)
    """
    g = build_capability_graph()
    return capability_health_report(g)
