"""
Capability Health — analysis consumer of the capability graph.

Reads CapabilityGraphResult (pure nodes + edges) and produces:
  - Health score (0-100) with grade
  - Unused / orphan / unresolved detection
  - Top hubs by degree
  - Impact blast radius per node

Graph/Analysis separation: this module NEVER modifies the graph.

Extensibility: checks are CapRule subclasses in cap_health_rules.py.
Add a new check: add a CapRule class → auto-discovered.
"""

from __future__ import annotations

from typing import Any, Dict


def capability_health_report(graph_result) -> Dict[str, Any]:
    """Produce a health report from a CapabilityGraphResult.
    Delegates to extensible CapHealthRegistry.

    To add a new health check: add a CapRule subclass in cap_health_rules.py.
    """
    from core.harness.knowledge.cap_health_rules import get_cap_registry
    return get_cap_registry().run(graph_result).to_dict()
