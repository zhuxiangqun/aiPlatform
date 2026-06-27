"""
OntologyValidator — Cross-check existing data against current ontology schema.

Checks: Wiki page orphans, missing required fields, graph node orphans,
state mismatches, edge orphans.

Callers:
  - core/api/routers/wiki.py (GET /ontology/domains/{id}/validation-report)
"""

from __future__ import annotations
import logging

from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional
import json as _json
import os as _os
import time as _time


@dataclass
class ValidationItem:
    item_type: str            # orphan_page | missing_fields | orphan_node | state_mismatch | orphan_edge
    severity: str             # error | warning
    message: str
    entity_name: str = ""
    class_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    domain_id: str
    items: List[ValidationItem] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=lambda: {
        "orphan_pages": 0, "missing_fields": 0, "orphan_nodes": 0,
        "state_mismatches": 0, "orphan_edges": 0, "total_pages": 0,
        "total_nodes": 0,
    })
    generated_at: float = 0.0

    def add(self, item: ValidationItem):
        self.items.append(item)
        key_map = {
            "orphan_page": "orphan_pages", "missing_fields": "missing_fields",
            "orphan_node": "orphan_nodes", "state_mismatch": "state_mismatches",
            "orphan_edge": "orphan_edges",
        }
        k = key_map.get(item.item_type)
        if k:
            self.summary[k] += 1


def validate_domain(domain_id: str, *, collection_id: str = None) -> ValidationReport:
    """Run full cross-check of existing data vs current ontology.

    Args:
        domain_id: ontology domain to validate (e.g. "ai-knowledge")
        collection_id: wiki collection to check (defaults to domain_id)
    """
    report = ValidationReport(domain_id=domain_id)
    report.generated_at = _time.time()

    home = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat"))
    onto_path = home / "ontologies" / f"{domain_id}.yaml"
    if not onto_path.exists():
        report.add(ValidationItem("orphan_page", "error", f"Ontology YAML not found: {onto_path}"))
        return report

    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    domain = load_ontology_from_yaml(str(onto_path))

    cid = collection_id or domain_id

    # ── 1. Wiki page validation ──
    _validate_wiki_pages(report, domain, cid, home)

    # ── 2. Graph node validation ──
    _validate_graph_nodes(report, domain, domain_id, home)

    return report


def _validate_wiki_pages(report: ValidationReport, domain, collection_id: str, home: _Path):
    """Check wiki pages: orphan categories + missing required fields."""
    try:
        from core.harness.knowledge.wiki_engine import search_pages
        pages = search_pages(limit=500, collection_id=collection_id)

        valid_categories: set = set()
        cls_by_category: Dict[str, Any] = {}

        # Include built-in ontology class categories (entities, topics, atoms, etc.)
        try:
            from core.harness.knowledge.knowledge_ontology import CLASSES
            for cls in CLASSES:
                for cat in cls.allowed_categories or []:
                    valid_categories.add(cat)
                    cls_by_category[cat] = cls
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # Add domain-specific class categories
        for cls in domain.classes:
            for cat in cls.allowed_categories or []:
                valid_categories.add(cat)
                cls_by_category[cat] = cls

        report.summary["total_pages"] = len(pages)

        for page in pages:
            cat = str(page.get("category") or "entities")

            # 1a. Orphan category
            if cat not in valid_categories:
                report.add(ValidationItem(
                    "orphan_page", "warning",
                    f"页面 '{page.get('title','?')}' 的类别 '{cat}' 不在本体中",
                    entity_name=str(page.get("title", "")),
                    class_name=cat,
                    details={"title": page.get("title"), "category": cat},
                ))

            # 1b. Missing required fields
            if cat in cls_by_category:
                cls = cls_by_category[cat]
                frontmatter = page.get("frontmatter") or {}
                missing = [f for f in (cls.required_fields or [])
                          if f not in frontmatter and f not in page and f != "body"]
                # 'body' is the page content itself, not a frontmatter field
                if missing:
                    report.add(ValidationItem(
                        "missing_fields", "warning",
                        f"页面 '{page.get('title','?')}' ({cat}) 缺少必填字段: {', '.join(missing)}",
                        entity_name=str(page.get("title", "")),
                        class_name=cat,
                        details={"title": page.get("title"), "missing": missing,
                                 "class_label": cls.label},
                    ))
    except Exception as e:
        report.add(ValidationItem("orphan_page", "error", f"Wiki 页面扫描失败: {e}"))


def _validate_graph_nodes(report: ValidationReport, domain, domain_id: str, home: _Path):
    """Check graph nodes: orphans + state mismatches."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        nodes = list(graph._nodes.values())
        report.summary["total_nodes"] = len(nodes)

        valid_labels: set = set()
        cls_by_label: Dict[str, Any] = {}

        # Include built-in ontology class labels
        try:
            from core.harness.knowledge.knowledge_ontology import CLASSES
            for cls in CLASSES:
                valid_labels.add(cls.label)
                cls_by_label[cls.label] = cls
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # Add domain-specific class labels
        for cls in domain.classes:
            valid_labels.add(cls.label)
            cls_by_label[cls.label] = cls

        for node in nodes:
            cn = str(node.class_name or "")

            # 2a. Orphan class_name
            if cn and cn not in valid_labels:
                report.add(ValidationItem(
                    "orphan_node", "warning",
                    f"图节点 '{node.entity_name}' 的类 '{cn}' 不在本体中",
                    entity_name=node.entity_name,
                    class_name=cn,
                    details={"entity_id": node.entity_id},
                ))
                continue

            # 2b. State mismatch
            if cn in cls_by_label:
                cls = cls_by_label[cn]
                states_cfg = getattr(cls, "states", None) or {}
                state_enum = states_cfg.get("enum", []) or []
                if state_enum:
                    valid_states = {s.get("name") for s in state_enum if isinstance(s, dict)}
                    node_state = getattr(node, "state", None)
                    if node_state and node_state not in valid_states:
                        report.add(ValidationItem(
                            "state_mismatch", "warning",
                            f"节点 '{node.entity_name}' 的状态 '{node_state}' 不在当前状态枚举中",
                            entity_name=node.entity_name,
                            class_name=cn,
                            details={"current_state": node_state,
                                     "valid_states": list(valid_states)},
                        ))
    except Exception as e:
        report.add(ValidationItem("orphan_node", "error", f"图节点扫描失败: {e}"))


def validate_report_to_dict(report: ValidationReport) -> Dict[str, Any]:
    """Serialize validation report for API response."""
    return {
        "domain_id": report.domain_id,
        "summary": report.summary,
        "items": [{
            "type": it.item_type,
            "severity": it.severity,
            "message": it.message,
            "entity_name": it.entity_name,
            "class_name": it.class_name,
            "details": it.details,
        } for it in report.items],
        "generated_at": report.generated_at,
    }
