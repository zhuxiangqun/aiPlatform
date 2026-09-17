"""Ontology three pillars (data / logic / action) — read-only aggregation.

Does not mutate GraphIndex or YAML. Logic changes must go through proposals;
action execution remains on ActionRegistry L1.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _domain_yaml_path(domain_id: str) -> Optional[Path]:
    home = _aiplat_home()
    candidates = [
        home / "ontologies" / f"{domain_id}.yaml",
        home / "ontologies" / domain_id / f"{domain_id}.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    # workspace seeds
    seeds = Path(__file__).resolve().parents[4] / "workspace_seeds" / "ontologies"
    for name in (f"{domain_id}.yaml", f"{domain_id}/{domain_id}.yaml"):
        p = seeds / name
        if p.is_file():
            return p
    return None


def get_ontology_pillars(domain_id: str) -> Dict[str, Any]:
    """Aggregate data (ABox counts), logic (axioms/rules), action (contracts)."""
    did = (domain_id or "").strip() or "it-ops"
    out: Dict[str, Any] = {
        "domain_id": did,
        "authority_note": "建议≠权威；写回须 Action / 本体提案",
        "data": {"entity_count": 0, "by_class": {}, "relation_count": 0},
        "logic": {
            "axioms": [],
            "inference_rules": [],
            "axiom_count": 0,
            "rule_count": 0,
            "soft_constraint_note": "公理/规则为 L2 软约束；Action blocked 为 L1 硬门",
        },
        "action": {"actions": [], "action_count": 0},
    }

    # ── data pillar ──
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        GraphIndex._loaded_instances.clear()
        g = GraphIndex.load(did)
        by_class: Dict[str, int] = {}
        rel_count = 0
        for node in (g._nodes or {}).values():
            cls = getattr(node, "class_name", "") or "?"
            by_class[cls] = by_class.get(cls, 0) + 1
            rel_count += len(getattr(node, "out_edges", None) or [])
        out["data"] = {
            "entity_count": len(g._nodes or {}),
            "by_class": by_class,
            "relation_count": rel_count,
        }
    except Exception:
        logger.debug("pillars data load failed for %s", did, exc_info=True)

    # ── logic pillar ──
    yaml_path = _domain_yaml_path(did)
    if yaml_path:
        try:
            from core.harness.knowledge.ontology_loader import load_ontology_from_yaml

            dom = load_ontology_from_yaml(str(yaml_path))
            axioms: List[Dict[str, Any]] = []
            for ax in dom.axioms or []:
                axioms.append(
                    {
                        "id": getattr(ax, "id", "") or "",
                        "severity": getattr(ax, "severity", "") or "warning",
                        "description": getattr(ax, "description", "") or "",
                        "constraint": "soft",
                    }
                )
            rules = []
            for r in dom.inference_rules or []:
                if isinstance(r, dict):
                    rules.append(
                        {
                            "id": str(r.get("id") or r.get("name") or ""),
                            "label": str(r.get("label") or r.get("description") or ""),
                            "constraint": "suggestion",
                        }
                    )
            out["logic"] = {
                "axioms": axioms[:50],
                "inference_rules": rules[:50],
                "axiom_count": len(axioms),
                "rule_count": len(rules),
                "yaml_path": str(yaml_path),
                "soft_constraint_note": "公理/规则为 L2 软约束；部署改 YAML 须走提案",
            }
        except Exception:
            logger.debug("pillars logic load failed for %s", did, exc_info=True)

    # ── action pillar ──
    try:
        from core.harness.ontology_engine.action_registry import get_action_registry
        from core.harness.ontology_engine.builtin_actions import register_all

        reg = get_action_registry()
        register_all(reg)
        actions: List[Dict[str, Any]] = []
        for c in reg._contracts.values():
            if getattr(c, "domain_id", None) != did:
                continue
            if not str(getattr(c, "action_id", "")).startswith("customer_action:"):
                continue
            actions.append(
                {
                    "action_id": c.action_id,
                    "label": getattr(c, "label", "") or c.action_id,
                    "target_class": getattr(c, "target_class", "") or "",
                    "required_state": getattr(c, "required_state", "") or "",
                    "risk_level": str(getattr(c, "risk_level", "") or ""),
                    "constraint": "hard",
                }
            )
        out["action"] = {"actions": actions, "action_count": len(actions)}
    except Exception:
        logger.debug("pillars action load failed for %s", did, exc_info=True)

    return out
