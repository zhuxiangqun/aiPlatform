"""Ontology Audit — structured domain health report for knowledge graph governance.



Generates per-domain statistics about class coverage, relation density,

state machine activity, and orphan detection. Used by the diagnostics

dashboard and ontology editor for data-driven decision making.



Usage:

    auditor = OntologyAuditor()

    report = auditor.audit_domain("ai-knowledge")

    # → {entity_counts, orphan_classes, relation_coverage, state_triggers, ...}

"""



from __future__ import annotations



import os

import logging

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional

from pathlib import Path





@dataclass

class OntologyAuditReport:

    domain_id: str = ""

    total_entities: int = 0

    total_edges: int = 0

    inferred_edges: int = 0

    class_entity_counts: Dict[str, int] = field(default_factory=dict)

    orphan_classes: List[str] = field(default_factory=list)

    relation_coverage: Dict[str, Dict[str, int]] = field(default_factory=dict)

    state_transition_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)

    unused_state_transitions: List[Dict[str, str]] = field(default_factory=list)

    warnings: List[str] = field(default_factory=list)

    recommendations: List[str] = field(default_factory=list)



    def to_dict(self) -> Dict[str, Any]:

        return {

            "domain_id": self.domain_id,

            "total_entities": self.total_entities,

            "total_edges": self.total_edges,

            "inferred_edges": self.inferred_edges,

            "class_entity_counts": self.class_entity_counts,

            "orphan_classes": self.orphan_classes,

            "relation_coverage": self.relation_coverage,

            "state_transition_counts": self.state_transition_counts,

            "unused_state_transitions": self.unused_state_transitions,

            "warnings": self.warnings,

            "recommendations": self.recommendations,

        }





class OntologyAuditor:

    """Audit ontology domains for knowledge graph health and governance."""



    def __init__(self):

        self._ontologies_dir = Path(os.getenv("AIPLAT_HOME", Path("~").expanduser() / ".aiplat")) / "ontologies"



    def audit_domain(self, domain_id: str) -> OntologyAuditReport:

        """Run full audit on one domain."""

        report = OntologyAuditReport(domain_id=domain_id)



        try:

            import yaml

            yaml_path = self._ontologies_dir / f"{domain_id}.yaml"

            if not yaml_path.exists():

                report.warnings.append(f"Domain YAML not found: {domain_id}")

                return report



            domain_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

            classes = domain_data.get("classes", {})



            # Load GraphIndex stats

            from core.harness.ontology_engine.graph_index import GraphIndex

            graph = GraphIndex.load(domain_id)



            total_nodes = 0

            total_edges = 0

            inferred_edges = 0

            class_counts: Dict[str, int] = {}



            for node in graph._nodes.values():

                total_nodes += 1

                # Count edges

                total_edges += len(node.out_edges)

                for e in node.out_edges:

                    if getattr(e, "inferred", False):

                        inferred_edges += 1



                # Count by class

                cls = node.class_name

                class_counts[cls] = class_counts.get(cls, 0) + 1



            report.total_entities = total_nodes

            report.total_edges = total_edges

            report.inferred_edges = inferred_edges

            report.class_entity_counts = dict(sorted(class_counts.items(), key=lambda x: x[1], reverse=True))



            # Detect orphan classes (defined in YAML but no entities)

            # v2.9: match by both YAML key AND label (GraphIndex stores labels)

            yaml_class_names = set(classes.keys())

            yaml_label_to_key = {}

            for cls_name, cls_def in classes.items():

                label = cls_def.get("label", cls_name)

                yaml_label_to_key[label] = cls_name



            graph_class_names = set(class_counts.keys())

            # Check YAML keys directly

            key_orphans = yaml_class_names - graph_class_names

            # Also check if labels match (entities store label, not key)

            real_orphans = [cn for cn in key_orphans if classes.get(cn, {}).get("label", cn) not in graph_class_names]

            report.orphan_classes = sorted(real_orphans)



            # Relation coverage: which YAML-defined relations have edges?

            object_properties = domain_data.get("object_properties", []) or []

            relation_counts: Dict[str, int] = {}

            all_relation_names = set()

            if isinstance(object_properties, list):

                for p in object_properties:

                    name = p.get("name", "")

                    if name:

                        all_relation_names.add(name)

                        relation_counts[name] = 0



            for node in graph._nodes.values():

                for e in node.out_edges:

                    rn = e.relation_name

                    if rn in relation_counts:

                        relation_counts[rn] += 1



            covered = {k: v for k, v in relation_counts.items() if v > 0}

            uncovered = {k: v for k, v in relation_counts.items() if v == 0}

            report.relation_coverage = {

                "total_defined": len(all_relation_names),

                "covered": len(covered),

                "uncovered": len(uncovered),

                "covered_relations": covered,

                "uncovered_relations": uncovered,

            }



            if uncovered:

                report.warnings.append(

                    f"{len(uncovered)} relations defined in YAML but zero edges: {list(uncovered.keys())[:5]}")



            # State machine: count transitions per class

            transition_counts: Dict[str, Dict[str, int]] = {}

            unused_transitions: List[Dict[str, str]] = []



            for cls_name, cls_def in classes.items():

                transitions = cls_def.get("transitions", []) or []

                if not transitions:

                    continue



                entity_count = class_counts.get(cls_name, 0)

                transition_counts[cls_name] = {

                    "defined_transitions": len(transitions),

                    "entities": entity_count,

                }



                if entity_count == 0:

                    for t in transitions:

                        unused_transitions.append({

                            "class": cls_name,

                            "from": t.get("from", "?"),

                            "to": t.get("to", "?"),

                            "trigger": str(t.get("trigger", {}))[:60],

                            "reason": "zero entities in this class",

                        })



            report.state_transition_counts = transition_counts

            report.unused_state_transitions = unused_transitions[:10]



            if unused_transitions:

                report.warnings.append(

                    f"{len(unused_transitions)} state transitions defined for classes with zero entities")



            # Recommendations

            if report.orphan_classes:

                report.recommendations.append(

                    f"{len(report.orphan_classes)} classes defined but have zero entities. "

                    f"Run ontology engine on more documents or check class labels for domain fit."

                )

            if uncovered:

                report.recommendations.append(

                    f"Relations {list(uncovered.keys())[:3]} have no edges. "

                    f"Add more documents containing co-occurring entities, or adjust relation definitions."

                )

            if len(class_counts) < 3:

                report.recommendations.append(

                    "Low entity diversity (<3 classes). Run ontology engine on more documents to enrich the graph."

                )



        except Exception as e:

            report.warnings.append(f"Audit failed: {str(e)[:200]}")



        return report



    def audit_all_domains(self) -> List[OntologyAuditReport]:

        """Run audit on all registered domains."""

        reports = []

        try:

            import json, yaml

            registry_path = self._ontologies_dir / "registry.json"

            if registry_path.exists():

                reg = json.loads(registry_path.read_text(encoding="utf-8")) or {}

                domains = reg.get("domains", {})

                for did in domains:

                    reports.append(self.audit_domain(did))

        except Exception:

            logging.getLogger(__name__).debug('audit_all_domains failed', exc_info=True)
        # v2.10: Event-driven health update

        if reports:

            try:

                from core.harness.evaluation.system_health import SystemHealthCalculator

                SystemHealthCalculator().recompute_on_event("ontology_audit_changed", source="audit_all_domains")

            except Exception:

                logging.getLogger(__name__).debug('audit_all_domains failed', exc_info=True)
        return reports

