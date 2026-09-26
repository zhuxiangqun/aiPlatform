"""Phase K3 — attach replayable reasoning paths to OrgRun. No execution rights."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def build_org_run_reasoning(
    domain_id: str,
    query: str,
    hits: List[Dict[str, Any]],
    *,
    max_paths: int = 8,
) -> Dict[str, Any]:
    """Copy graph neighborhood paths onto a run. Never authorizes actions."""
    did = (domain_id or "").strip() or "it-ops"
    q = (query or "").strip()
    seed = [h for h in (hits or []) if isinstance(h, dict) and h.get("entity_id")]
    if not seed:
        return {
            "status": "skipped",
            "skipped": "no_entity",
            "domain_id": did,
            "query": q,
            "reasoning_paths": [],
            "entities": [],
            "can_execute": False,
            "authority_note": "K3: no locate hits; path skipped; not an action permit",
        }

    paths: List[str] = []
    entities: List[Dict[str, Any]] = []
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        g = GraphIndex.load(did)
        nodes = getattr(g, "_nodes", {}) or {}
        for h in seed[:12]:
            eid = str(h.get("entity_id") or "")
            name = str(h.get("entity_name") or eid)
            entities.append(
                {
                    "entity_id": eid,
                    "entity_name": name,
                    "class_name": str(h.get("class_name") or ""),
                }
            )
            node = nodes.get(eid)
            if node is None:
                paths.append(f"{name}({eid}) [node_missing]")
                continue
            outs = list(getattr(node, "out_edges", []) or [])[:4]
            if not outs:
                paths.append(f"{name}({eid})")
                continue
            for edge in outs:
                rel = (
                    getattr(edge, "relation_name", None)
                    or getattr(edge, "rel_type", None)
                    or getattr(edge, "predicate", None)
                    or "related"
                )
                tgt = getattr(edge, "target_id", None) or getattr(edge, "to_id", None) or ""
                tgt_name = tgt
                tnode = nodes.get(str(tgt)) if tgt else None
                if tnode is not None:
                    tgt_name = str(
                        getattr(tnode, "entity_name", None)
                        or getattr(tnode, "name", None)
                        or tgt
                    )
                paths.append(f"{name} -[{rel}]-> {tgt_name}({tgt})")
                if len(paths) >= max_paths:
                    break
            if len(paths) >= max_paths:
                break
    except Exception:
        logger.warning("K3 reasoning path build failed domain=%s", did, exc_info=True)
        return {
            "status": "skipped",
            "skipped": "graph_error",
            "domain_id": did,
            "query": q,
            "reasoning_paths": [],
            "entities": [
                {"entity_id": str(h.get("entity_id") or ""), "entity_name": str(h.get("entity_name") or "")}
                for h in seed[:8]
            ],
            "can_execute": False,
            "authority_note": "K3: graph path build failed; not an action permit",
        }

    if not paths:
        return {
            "status": "skipped",
            "skipped": "no_path",
            "domain_id": did,
            "query": q,
            "reasoning_paths": [],
            "entities": entities,
            "can_execute": False,
            "authority_note": "K3: entities found but no edges; not an action permit",
        }

    return {
        "status": "ok",
        "skipped": "",
        "domain_id": did,
        "query": q,
        "reasoning_paths": paths[:max_paths],
        "entities": entities,
        "path_count": len(paths[:max_paths]),
        "can_execute": False,
        "authority_note": "K3: reasoning_paths are evidence only; triage_gate / Interface still gate actions",
    }
