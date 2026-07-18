u"""
Ontology Importer — 外部本体联邦导入 (v2.6).

Supports importing industry standard ontologies:
  - OWL/RDF (rdfs:label, owl:Class, owl:ObjectProperty)
  - SKOS (skos:Concept, skos:prefLabel, skos:broader/narrower)
  - JSON-LD (custom)
  
Imported ontologies are marked readonly and stored as YAML.
"""
from __future__ import annotations

import json as _json
import logging
import os as _os
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger("ontology_importer")


def import_ontology(source: str, *, target_domain: str, format: str = "auto") -> Dict[str, Any]:
    u"""Import an external ontology into the aiPlat ontology system.

    Args:
        source: URL or local file path to the external ontology
        target_domain: domain_id for the imported ontology
        format: "owl" | "skos" | "jsonld" | "auto" (detect from extension/content)

    Returns:
        {"domain_id": "...", "class_count": N, "property_count": N, "path": "...", "readonly": true}
    """
    ontologies_dir = Path(_os.path.expanduser(
        _os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies")
    ))
    ontologies_dir.mkdir(parents=True, exist_ok=True)

    if source.startswith(("http://", "https://")):
        import urllib.request
        content = urllib.request.urlopen(source, timeout=30).read().decode("utf-8", errors="replace")
        source_name = source.rstrip("/").split("/")[-1] or target_domain
    else:
        src_path = Path(source)
        if not src_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        content = src_path.read_text(encoding="utf-8", errors="replace")
        source_name = src_path.stem

    if format == "auto":
        if content.strip().startswith(("{", "[")):
            format = "jsonld"
        elif "<rdf:RDF" in content[:500] or "<rdf:" in content[:500]:
            format = "owl"
        elif "<skos:" in content[:500]:
            format = "skos"
        else:
            raise ValueError("Cannot auto-detect format. Please specify format=owl|skos|jsonld")

    data = _parse_external(content, format, target_domain)
    data["description"] = f"Imported from {source} ({format})"
    data["_imported"] = True
    data["_readonly"] = True
    data["_source"] = source
    data["_format"] = format

    yaml_path = ontologies_dir / f"{target_domain}.yaml"
    from core.harness.knowledge.yaml_serializer import dict_to_yaml
    yaml_str = dict_to_yaml(data)
    yaml_path.write_text(yaml_str, encoding="utf-8")

    class_count = len(data.get("classes", {}))
    prop_count = len(data.get("object_properties", [])) + len(data.get("data_properties", []))

    logger.info("Imported ontology '%s': %d classes, %d properties → %s",
                 target_domain, class_count, prop_count, yaml_path)

    return {
        "domain_id": target_domain,
        "class_count": class_count,
        "property_count": prop_count,
        "path": str(yaml_path),
        "readonly": True,
        "format": format,
    }


def _parse_external(content: str, format: str, domain_id: str) -> Dict[str, Any]:
    u"""Parse external ontology content into aiPlat YAML dict structure."""
    if format == "owl":
        return _parse_owl(content, domain_id)
    elif format == "skos":
        return _parse_skos(content, domain_id)
    elif format == "jsonld":
        return _parse_jsonld(content, domain_id)
    else:
        raise ValueError(f"Unsupported format: {format}")


def _parse_owl(content: str, domain_id: str) -> Dict[str, Any]:
    u"""Parse OWL/RDF XML into classes + object_properties."""
    classes = {}
    properties = []
    ns = f"http://aiplat.local/ontology/{domain_id}/"

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        content = content.replace("&", "&amp;")
        root = ET.fromstring(content)

    ns_map = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
              "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
              "owl": "http://www.w3.org/2002/07/owl#"}

    for cls_elem in root.iter():
        tag = cls_elem.tag.split("}")[-1] if "}" in cls_elem.tag else cls_elem.tag
        cls_uri = cls_elem.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        if not cls_uri and tag == "Class":
            cls_uri = cls_elem.get("about", "")
        if not cls_uri:
            continue

        class_name = cls_uri.split("#")[-1] or cls_uri.split("/")[-1]
        if not class_name or class_name.startswith("http"):
            continue

        label_elem = cls_elem.find(".//{http://www.w3.org/2000/01/rdf-schema#}label")
        label = label_elem.text.strip() if label_elem is not None and label_elem.text else class_name
        desc_elem = cls_elem.find(".//{http://www.w3.org/2000/01/rdf-schema#}comment")
        description = desc_elem.text.strip()[:200] if desc_elem is not None and desc_elem.text else ""

        parent_elem = cls_elem.find(".//{http://www.w3.org/2000/01/rdf-schema#}subClassOf")
        parent = ""
        if parent_elem is not None:
            parent_uri = parent_elem.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource", "")
            if parent_uri:
                parent = parent_uri.split("#")[-1]

        classes[class_name] = {
            "label": label,
            "description": description,
            "required_fields": ["name", "description"],
            "optional_fields": [],
            "categories": [domain_id],
            "fields": [],
        }
        if parent:
            classes[class_name]["parent"] = parent

    for prop_elem in root.iter():
        tag = prop_elem.tag.split("}")[-1] if "}" in prop_elem.tag else prop_elem.tag
        if tag not in ("ObjectProperty", "DatatypeProperty"):
            continue
        prop_uri = prop_elem.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        if not prop_uri:
            prop_uri = prop_elem.get("about", "")
        if not prop_uri:
            continue
        prop_name = prop_uri.split("#")[-1]
        label_elem = prop_elem.find(".//{http://www.w3.org/2000/01/rdf-schema#}label")
        prop_label = label_elem.text.strip() if label_elem is not None and label_elem.text else prop_name
        properties.append({"name": prop_name, "label": prop_label, "domain": [], "range": []})

    return {
        "name": domain_id,
        "namespace": ns,
        "version": "1.0.0",
        "classes": classes,
        "object_properties": properties,
        "data_properties": [],
        "inference_rules": [],
    }


def _parse_skos(content: str, domain_id: str) -> Dict[str, Any]:
    u"""Parse SKOS taxonomy into classes with hierarchy."""
    classes = {}
    ns = f"http://aiplat.local/ontology/{domain_id}/"

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        root = ET.fromstring(content.replace("&", "&amp;"))

    for concept in root.iter():
        tag = concept.tag.split("}")[-1] if "}" in concept.tag else concept.tag
        if tag != "Concept":
            continue
        uri = concept.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "") or concept.get("about", "")
        name = uri.split("#")[-1] or uri.split("/")[-1]
        if not name:
            continue
        pref = concept.find(".//{http://www.w3.org/2004/02/skos/core#}prefLabel")
        label = pref.text.strip() if pref is not None and pref.text else name
        definition = concept.find(".//{http://www.w3.org/2004/02/skos/core#}definition")
        description = definition.text.strip()[:200] if definition is not None and definition.text else ""

        parent = ""
        broader = concept.find(".//{http://www.w3.org/2004/02/skos/core#}broader")
        if broader is not None:
            parent_uri = broader.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource", "")
            if parent_uri:
                parent = parent_uri.split("#")[-1]

        classes[name] = {
            "label": label,
            "description": description,
            "required_fields": ["name", "description"],
            "optional_fields": [],
            "categories": [domain_id],
            "fields": [],
        }
        if parent:
            classes[name]["parent"] = parent

    return {
        "name": domain_id,
        "namespace": ns,
        "version": "1.0.0",
        "classes": classes,
        "object_properties": [],
        "data_properties": [],
        "inference_rules": [],
    }


def _parse_jsonld(content: str, domain_id: str) -> Dict[str, Any]:
    u"""Parse JSON-LD into classes + properties."""
    data = _json.loads(content)
    classes = {}
    properties = []
    ns = f"http://aiplat.local/ontology/{domain_id}/"

    graph = data if isinstance(data, list) else data.get("@graph", [data])
    for node in graph:
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type", "")
        if isinstance(node_type, list):
            node_type = node_type[0] if node_type else ""

        if "Class" in node_type or "rdfs:Class" in node_type:
            name = node.get("@id", "").split("#")[-1] or node.get("@id", "").split("/")[-1]
            label = node.get("rdfs:label", node.get("label", name))
            if isinstance(label, dict):
                label = label.get("@value", name)
            description = node.get("rdfs:comment", node.get("comment", ""))
            if isinstance(description, dict):
                description = description.get("@value", "")
            classes[name] = {
                "label": str(label),
                "description": str(description)[:200],
                "required_fields": ["name", "description"],
                "optional_fields": [],
                "categories": [domain_id],
                "fields": [],
            }

        if "ObjectProperty" in node_type or "DatatypeProperty" in node_type:
            name = node.get("@id", "").split("#")[-1]
            label = node.get("rdfs:label", node.get("label", name))
            if isinstance(label, dict):
                label = label.get("@value", name)
            properties.append({"name": name or f"prop_{len(properties)}", "label": str(label), "domain": [], "range": []})

    return {
        "name": domain_id,
        "namespace": ns,
        "version": "1.0.0",
        "classes": classes,
        "object_properties": properties,
        "data_properties": [],
        "inference_rules": [],
    }
