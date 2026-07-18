u"""
YAML Serializer — OntologyDomain ↔ YAML string ↔ JSON dict 双向转换。

支撑本体编辑器 (Ontology Editor) 的 CRUD 操作，确保编辑后的 JSON 能
无损回写为 YAML 格式，保持与 load_ontology_from_yaml 的兼容性。
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("yaml_serializer")


def domain_to_dict(domain) -> Dict[str, Any]:
    u"""OntologyDomain → 完整 JSON dict（供前端编辑和 API 返回）。"""
    result = {
        "id": domain.id,
        "name": domain.name,
        "namespace": domain.namespace,
        "description": domain.description,
        "version": domain.version,
        "classes": {},
        "object_properties": [],
        "data_properties": [],
        "inference_rules": list(domain.inference_rules or []),
    }

    for cls in domain.classes:
        cls_name = _short_name(cls.uri, domain.namespace)
        class_entry: Dict[str, Any] = {
            "label": cls.label,
            "description": cls.description,
            "required_fields": list(cls.required_fields),
            "optional_fields": list(cls.optional_fields),
            "categories": list(cls.allowed_categories),
            "fields": _serialize_fields(cls.fields),
        }
        if cls.parent:
            class_entry["parent"] = _short_name(cls.parent, domain.namespace)
        if cls.synonyms:
            class_entry["synonyms"] = list(cls.synonyms)
        if cls.confidence_threshold != 0.7:
            class_entry["confidence_threshold"] = cls.confidence_threshold
        if cls.implements:
            class_entry["implements"] = list(cls.implements)
        if cls.standard_mapping:
            class_entry["standard_mapping"] = cls.standard_mapping
        if cls.template_markdown:
            class_entry["template_markdown"] = cls.template_markdown
        if cls.extraction_prompt:
            class_entry["extraction_prompt"] = cls.extraction_prompt

        states_cfg = cls.states or {}
        transitions = list(cls.transitions or [])
        side_effects = list(cls.side_effects or [])

        if states_cfg or transitions or side_effects:
            class_entry["states"] = {}
            if states_cfg.get("default"):
                class_entry["states"]["default"] = states_cfg["default"]
            if states_cfg.get("enum"):
                class_entry["states"]["enum"] = list(states_cfg["enum"])
            if transitions:
                class_entry["states"]["transitions"] = _clean_transitions(transitions)
            if side_effects:
                class_entry["states"]["side_effects"] = _clean_side_effects(side_effects)

        result["classes"][cls_name] = class_entry

    for prop in domain.object_properties:
        result["object_properties"].append(_serialize_obj_prop(prop, domain.namespace))
    for prop in domain.data_properties:
        result["data_properties"].append(_serialize_data_prop(prop, domain.namespace))

    return result


def dict_to_yaml(data: Dict[str, Any]) -> str:
    u"""JSON dict → YAML string（保持与 hand-authored YAML 兼容的格式）。"""
    import yaml

    clean = _dict_for_yaml(data)

    class CustomDumper(yaml.Dumper):
        pass

    def _str_representer(dumper, value):
        if "\n" in value:
            return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", value)

    CustomDumper.add_representer(str, _str_representer)

    return yaml.dump(
        clean,
        Dumper=CustomDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


def write_domain_yaml(domain, output_path: str) -> str:
    u"""OntologyDomain → YAML string → write to file. Returns written path."""
    data = domain_to_dict(domain)
    yaml_str = dict_to_yaml(data)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_str, encoding="utf-8")
    logger.info("Wrote %d classes to %s", len(domain.classes), output_path)
    return str(path)


def merge_class_into_domain(
    domain_dict: Dict[str, Any],
    class_name: str,
    class_data: Dict[str, Any],
) -> Dict[str, Any]:
    u"""Merge or add a class definition into a domain dict. Returns modified dict."""
    result = copy.deepcopy(domain_dict)
    result.setdefault("classes", {})
    result["classes"][class_name] = class_data
    return result


def remove_class_from_domain(
    domain_dict: Dict[str, Any],
    class_name: str,
) -> Dict[str, Any]:
    u"""Remove a class from a domain dict. Returns modified dict."""
    result = copy.deepcopy(domain_dict)
    result.get("classes", {}).pop(class_name, None)
    return result


# ── Internal helpers ───────────────────────────────────────────────────

def _short_name(uri: str, namespace: str) -> str:
    if uri.startswith(namespace):
        return uri[len(namespace):]
    return uri.split("#")[-1] if "#" in uri else uri.split("/")[-1]


def _serialize_fields(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for f in fields:
        entry = {"name": f.get("name", ""), "type": f.get("type", "string")}
        if f.get("description"):
            entry["description"] = f["description"]
        if f.get("values"):
            entry["values"] = f["values"]
        if f.get("default") is not None:
            entry["default"] = f["default"]
        result.append(entry)
    return result


def _clean_transitions(transitions: List[Dict]) -> List[Dict]:
    result = []
    for t in transitions:
        entry = {
            "from": t.get("from", []),
            "to": t.get("to", ""),
            "description": t.get("description", ""),
        }
        trigger = t.get("trigger", {})
        if trigger:
            entry["trigger"] = {
                "type": trigger.get("type", ""),
            }
            for k in ("relation", "field", "condition", "threshold", "operator"):
                if trigger.get(k) is not None:
                    entry["trigger"][k] = trigger[k]
        result.append(entry)
    return result


def _clean_side_effects(effects: List[Dict]) -> List[Dict]:
    result = []
    for se in effects:
        entry = {"when": se.get("when", "")}
        actions = se.get("actions", [])
        if actions:
            entry["actions"] = []
            for a in actions:
                action_entry = {"type": a.get("type", "add_tag")}
                for k in ("tag", "url", "template"):
                    if a.get(k):
                        action_entry[k] = a[k]
                entry["actions"].append(action_entry)
        result.append(entry)
    return result


def _serialize_obj_prop(prop, namespace: str) -> Dict[str, Any]:
    entry = {
        "name": _short_name(prop.uri, namespace) if hasattr(prop, "uri") else prop.name,
        "label": prop.label,
    }
    if hasattr(prop, "domain") and prop.domain:
        entry["domain"] = [_short_name(d, namespace) for d in prop.domain]
    if hasattr(prop, "range") and prop.range:
        entry["range"] = [_short_name(r, namespace) for r in prop.range]
    if hasattr(prop, "inverse") and prop.inverse:
        entry["inverse"] = prop.inverse
    if hasattr(prop, "transitive") and prop.transitive:
        entry["transitive"] = True
    if hasattr(prop, "symmetric") and prop.symmetric:
        entry["symmetric"] = True
    return entry


def _serialize_data_prop(prop, namespace: str) -> Dict[str, Any]:
    entry = {
        "name": _short_name(prop.uri, namespace) if hasattr(prop, "uri") else prop.name,
        "label": prop.label,
        "range": "xsd:string",
    }
    if hasattr(prop, "domain") and prop.domain:
        entry["domain"] = [_short_name(d, namespace) for d in prop.domain]
    if hasattr(prop, "functional") and prop.functional:
        entry["functional"] = True
    return entry


def _dict_for_yaml(data: Dict[str, Any]) -> Dict[str, Any]:
    u"""Strip internal fields before YAML serialization."""
    result = {}
    for key in ("name", "namespace", "description", "version", "classes",
                "object_properties", "data_properties", "inference_rules"):
        if key in data:
            result[key] = data[key]
    return result
