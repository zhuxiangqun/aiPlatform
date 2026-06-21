"""
Ontology YAML Loader — 从 YAML 配置文件加载声明式领域本体。

Architecture:
  ~/.aiplat/ontologies/
  ├── default.yaml          ← 系统默认知识本体
  ├── ship-design.yaml      ← 船舶设计领域本体
  └── equipment-maintenance.yaml  ← 设备运维领域本体

Each YAML file maps to Python OntologyClass/Property objects,
enabling domain experts to define ontologies without writing code.
"""

from __future__ import annotations

import os as _os
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

# Re-use existing ontology types from knowledge_ontology
from core.harness.knowledge.knowledge_ontology import (
    OntologyClass,
    OntologyObjectProperty,
    OntologyDataProperty,
    OntologyAxiom,
)


# ── Domain-level container ────────────────────────────────────────────

@dataclass
class OntologyDomain:
    """A named ontology domain loaded from YAML."""
    id: str                          # e.g. "ship-design"
    name: str                        # 船舶设计
    namespace: str                   # http://aiplat.local/ontology/ship-design#
    description: str = ""
    version: str = "1.0.0"
    classes: List[OntologyClass] = field(default_factory=list)
    object_properties: List[OntologyObjectProperty] = field(default_factory=list)
    data_properties: List[OntologyDataProperty] = field(default_factory=list)
    axioms: List[OntologyAxiom] = field(default_factory=list)
    inference_rules: List[Dict[str, Any]] = field(default_factory=list)


# ── YAML Loader ──────────────────────────────────────────────────────

def _resolve_uri(namespace: str, short: str) -> str:
    """Resolve short name to full URI."""
    if short.startswith("http"):
        return short
    return f"{namespace}{short}"


def load_ontology_from_yaml(file_path: str) -> OntologyDomain:
    """Load a domain ontology from a YAML file."""
    import yaml

    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        raise ValueError(f"Invalid ontology YAML: {file_path}")

    ns = raw.get("namespace", "http://aiplat.local/ontology/")
    domain_id = _Path(file_path).stem
    domain = OntologyDomain(
        id=domain_id,
        name=raw.get("name", domain_id),
        namespace=ns,
        description=raw.get("description", ""),
        version=raw.get("version", "1.0.0"),
        inference_rules=list(raw.get("inference_rules") or []),
    )

    # ── Load classes ──
    classes_raw = raw.get("classes", {})
    if isinstance(classes_raw, dict):
        for cls_name, cls_def in classes_raw.items():
            uri = _resolve_uri(ns, cls_name)
            parent_uri = _resolve_uri(ns, cls_def.get("parent", "")) if cls_def.get("parent") else None
            states_cfg = cls_def.get("states") or {}
            domain.classes.append(OntologyClass(
                uri=uri,
                label=cls_def.get("label", cls_name),
                parent=parent_uri,
                required_fields=list(cls_def.get("required_fields", []) or []),
                optional_fields=list(cls_def.get("optional_fields", []) or []),
                allowed_categories=list(cls_def.get("allowed_categories", []) or cls_def.get("categories", []) or []),
                template_markdown=str(cls_def.get("template_markdown", "") or ""),
                extraction_prompt=str(cls_def.get("extraction_prompt", "") or ""),
                standard_mapping=cls_def.get("standard_mapping"),
                description=str(cls_def.get("description", "") or ""),
                fields=list(cls_def.get("fields", []) or []),
                states=states_cfg,
                transitions=list(states_cfg.get("transitions") or cls_def.get("transitions") or []),
                side_effects=list(states_cfg.get("side_effects") or cls_def.get("side_effects") or []),
                synonyms=list(cls_def.get("synonyms", []) or []),
                confidence_threshold=float(cls_def.get("confidence_threshold", 0.7)),
            ))

    # ── Load object properties ──
    props_raw = raw.get("object_properties", [])
    if isinstance(props_raw, list):
        for prop_def in props_raw:
            domain.object_properties.append(OntologyObjectProperty(
                uri=_resolve_uri(ns, prop_def.get("name", "")),
                label=prop_def.get("label", prop_def.get("name", "")),
                domain=[_resolve_uri(ns, d) for d in (prop_def.get("domain", []) or [])],
                range=[_resolve_uri(ns, r) for r in (prop_def.get("range", []) or [])],
                is_symmetric=bool(prop_def.get("symmetric", False)),
                is_transitive=bool(prop_def.get("transitive", False)),
                inverse_of=_resolve_uri(ns, prop_def.get("inverse", "") if prop_def.get("inverse") else ""),
                inverse_label=str(prop_def.get("inverse_label", "") or prop_def.get("inverse", "") or ""),
                max_cardinality=prop_def.get("max_cardinality"),
            ))

    # ── Load data properties ──
    dprops_raw = raw.get("data_properties", [])
    if isinstance(dprops_raw, list):
        for dprop_def in dprops_raw:
            domain.data_properties.append(OntologyDataProperty(
                uri=_resolve_uri(ns, dprop_def.get("name", "")),
                label=dprop_def.get("label", dprop_def.get("name", "")),
                domain=[_resolve_uri(ns, d) for d in (dprop_def.get("domain", []) or [])],
                range=dprop_def.get("range", "xsd:string"),
                is_functional=bool(dprop_def.get("functional", False)),
            ))

    return domain


def list_domain_files(base_dir: str = "") -> List[str]:
    """List available ontology domain files."""
    d = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"
    if not d.exists():
        return []
    return sorted([f.stem for f in d.glob("*.yaml")])


def load_all_domains(base_dir: str = "") -> Dict[str, OntologyDomain]:
    """Load all ontology domain files."""
    domains = {}
    for domain_id in list_domain_files(base_dir):
        d = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"
        file_path = d / f"{domain_id}.yaml"
        try:
            domains[domain_id] = load_ontology_from_yaml(str(file_path))
        except Exception:
            pass
    return domains
