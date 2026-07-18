"""
Knowledge Markings — lineage-based security propagation for ontology entities.

Implements Palantir-style markings:
  1. Marking model: label + level + scope per entity
  2. Propagation engine: BFS along reversed ontology relations
  3. MarkingTrace: audit trail showing where each marking came from
  4. Storage: per-collection JSON file (markings.json)

Design: Markings answer "which entities are sensitive?", 
complementing RBAC which answers "who is authorized?".
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.harness.knowledge.knowledge_ontology import KnowledgeOntology, OntologyTriple

AI = "http://aiplat.local/knowledge#"

logger = logging.getLogger(__name__)


class MarkingLevel(IntEnum):
    PUBLIC = 1
    INTERNAL = 2
    CONFIDENTIAL = 3
    RESTRICTED = 4


@dataclass
class Marking:
    label: str
    level: MarkingLevel
    scope: str = ""
    propagated_from: Optional[str] = None
    propagated_via: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "level": self.level.value,
            "level_name": self.level.name,
            "scope": self.scope,
            "propagated_from": self.propagated_from,
            "propagated_via": self.propagated_via,
        }


@dataclass
class MarkingTrace:
    marking_label: str
    level: MarkingLevel
    origin_entity_uri: str
    propagation_path: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "marking_label": self.marking_label,
            "level": self.level.name,
            "origin_entity_uri": self.origin_entity_uri,
            "propagation_path": self.propagation_path,
        }


@dataclass
class MarkingConfig:
    collection_id: str
    markings: Dict[str, List[Marking]] = field(default_factory=dict)
    propagation_rules: Dict[str, bool] = field(default_factory=lambda: {
        "hasSource": True,
        "cites": True,
        "hasAtom": True,
        "derivesFrom": True,
        "parentOf": True,
        "childOf": True,
        "contradicts": False,
        "supports": True,
        "extends": True,
        "example_of": True,
    })

    @classmethod
    def default(cls, collection_id: str = "default") -> "MarkingConfig":
        return cls(collection_id=collection_id)


def _markings_path(collection_id: str = "default") -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "markings.json")


def load_markings_config(collection_id: str = "default") -> MarkingConfig:
    path = _markings_path(collection_id)
    config = MarkingConfig(collection_id=collection_id)
    if not _os.path.exists(path):
        return config

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        parsed: Dict[str, List[Marking]] = {}
        for uri_str, marking_list in data.get("markings", {}).items():
            parsed[uri_str] = []
            for m in marking_list:
                if isinstance(m, dict):
                    parsed[uri_str].append(Marking(
                        label=m.get("label", ""),
                        level=MarkingLevel(m.get("level", 1)),
                        scope=m.get("scope", ""),
                        propagated_from=m.get("propagated_from"),
                        propagated_via=m.get("propagated_via"),
                    ))
        config.markings = parsed
        if "propagation_rules" in data:
            config.propagation_rules = data["propagation_rules"]
    except Exception:
        logger.warning("Failed to load markings config for %s", collection_id)

    return config


def save_markings_config(config: MarkingConfig) -> None:
    path = _markings_path(config.collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)

    serialized = {
        "version": "v1.0",
        "updated_at": _time.time(),
        "propagation_rules": config.propagation_rules,
        "markings": {
            uri: [m.to_dict() for m in marks]
            for uri, marks in config.markings.items()
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(serialized, f, indent=2, ensure_ascii=False)


def set_marking(
    entity_uri: str,
    label: str,
    level: MarkingLevel,
    scope: str = "",
    *,
    collection_id: str = "default",
) -> Marking:
    config = load_markings_config(collection_id)
    marking = Marking(label=label, level=level, scope=scope)

    existing = config.markings.get(entity_uri, [])
    replaced = False
    for i, m in enumerate(existing):
        if m.label == label:
            existing[i] = marking
            replaced = True
            break
    if not replaced:
        existing.append(marking)
    config.markings[entity_uri] = existing

    save_markings_config(config)
    return marking


def remove_marking(
    entity_uri: str,
    label: str = "",
    *,
    collection_id: str = "default",
) -> bool:
    config = load_markings_config(collection_id)
    if entity_uri not in config.markings:
        return False

    if not label:
        del config.markings[entity_uri]
        save_markings_config(config)
        return True

    existing = config.markings.get(entity_uri, [])
    new_list = [m for m in existing if m.label != label]
    if len(new_list) == len(existing):
        return False
    if new_list:
        config.markings[entity_uri] = new_list
    else:
        del config.markings[entity_uri]
    save_markings_config(config)
    return True


def get_entity_markings(
    entity_uri: str,
    *,
    collection_id: str = "default",
    resolve_effective: bool = True,
) -> Dict[str, Any]:
    config = load_markings_config(collection_id)
    explicit = config.markings.get(entity_uri, [])

    result: Dict[str, Any] = {
        "entity_uri": entity_uri,
        "explicit_markings": [m.to_dict() for m in explicit],
    }

    if resolve_effective:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
        effective, traces = resolve_effective_markings(entity_uri, config, onto.triples)

        result["effective_markings"] = [m.to_dict() for m in effective]
        result["inherited_traces"] = [t.to_dict() for t in traces]
        result["propagation_rules"] = {
            k: v for k, v in config.propagation_rules.items()
        }

    return result


def resolve_effective_markings(
    entity_uri: str,
    config: MarkingConfig,
    onto_triples: List[Any],
    max_depth: int = 5,
) -> Tuple[List[Marking], List[MarkingTrace]]:
    u"""BFS along reversed ontology edges to compute all inherited markings.

    For each entity that points TO entity_uri (incoming edges), check if
    the relation type propagates markings. If so, inherit and continue BFS.

    Returns:
      (effective_markings, traces) — highest-level marking per label + audit trails.
    """
    effective: Dict[str, Marking] = {}
    traces: Dict[str, MarkingTrace] = {}
    visited: Set[str] = set()
    queue: deque = deque([(entity_uri, 0)])

    # Build adjacency index: object → [(subject, predicate)]
    incoming: Dict[str, List[Tuple[str, str]]] = {}
    for t in onto_triples:
        incoming.setdefault(t.object, []).append((t.subject, t.predicate))

    while queue:
        current, depth = queue.popleft()
        if current in visited or depth > max_depth:
            continue
        visited.add(current)

        # Aggregate direct markings on current node
        for m in config.markings.get(current, []):
            existing = effective.get(m.label)
            if existing is None or m.level > existing.level:
                effective[m.label] = Marking(
                    label=m.label,
                    level=m.level,
                    scope=m.scope,
                    propagated_from=m.propagated_from or current.replace(AI, "")[:60],
                    propagated_via=m.propagated_via,
                )
                traces[m.label] = MarkingTrace(
                    marking_label=m.label,
                    level=m.level,
                    origin_entity_uri=m.propagated_from or current.replace(AI, "")[:60],
                    propagation_path=[current.replace(AI, "")[:60]],
                )

        if depth >= max_depth:
            continue

        # BFS incoming edges
        for src_uri, pred_uri in incoming.get(current, []):
            pred_name = pred_uri.replace(AI, "")
            if config.propagation_rules.get(pred_name, True):
                # Enrich traces with path info
                for label in effective:
                    if label not in config.markings.get(src_uri, []):
                        if src_uri not in visited:
                            pass
                queue.append((src_uri, depth + 1))

    return list(effective.values()), list(traces.values())


def compute_marking_diff(
    entity_uri: str,
    explicit_markings: List[Marking],
    effective_markings: List[Marking],
) -> List[Dict[str, Any]]:
    explicit_labels = {m.label for m in explicit_markings}
    diff = []
    for m in effective_markings:
        if m.label not in explicit_labels:
            diff.append({
                "label": m.label,
                "level": m.level.name,
                "propagated_from": m.propagated_from,
                "propagated_via": m.propagated_via,
            })
    return diff


def get_propagation_tree(
    entity_uri: str,
    *,
    collection_id: str = "default",
    max_depth: int = 4,
) -> Dict[str, Any]:
    u"""Return full propagation tree showing all inherited markings + their sources."""
    config = load_markings_config(collection_id)
    from core.harness.knowledge.knowledge_ontology import get_ontology
    onto = get_ontology()

    explicit = config.markings.get(entity_uri, [])
    effective, traces = resolve_effective_markings(entity_uri, config, onto.triples, max_depth)
    diff = compute_marking_diff(entity_uri, explicit, effective)

    return {
        "entity_uri": entity_uri,
        "explicit": [m.to_dict() for m in explicit],
        "effective": [m.to_dict() for m in effective],
        "propagation_traces": [t.to_dict() for t in traces],
        "inherited": diff,
        "propagation_rules": config.propagation_rules,
    }
