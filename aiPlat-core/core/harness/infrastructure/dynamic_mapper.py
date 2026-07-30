"""
Dynamic Schema Mapper (v3.1, 2026-07-30) — Palantir MSS-aligned runtime ontology mapping.

Maps external raw JSON to internal ontology entities without pre-modeling.
Three-stage key matching: exact → normalized → fuzzy.
"""
from __future__ import annotations

import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
from core.harness.ontology_engine.graph_index import GraphIndex

logger = logging.getLogger(__name__)


class DynamicSchemaMapper:
    """Runtime mapper: external JSON → GraphIndex entity via ontology YAML."""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    def _load_class_schema(self, domain_id: str, class_name: str) -> Dict[str, Any]:
        """Load target class attribute schema from domain YAML."""
        cache_key = f"{domain_id}:{class_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        yaml_path = os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Domain ontology not found: {yaml_path}")

        ontology = load_ontology_from_yaml(yaml_path)
        class_def = None
        classes = getattr(ontology, "classes", []) or []
        for c in classes:
            name = getattr(c, "label", "") or getattr(c, "name", "")
            if name == class_name or getattr(c, "name", "") == class_name:
                class_def = c
                break

        if not class_def:
            # Save empty schema so we don't retry repeatedly
            self._cache[cache_key] = {"properties": {}, "required": []}
            return self._cache[cache_key]

        schema = {"properties": {}, "required": []}
        for attr in getattr(class_def, "fields", []) or []:
            name = getattr(attr, "name", "") or attr.get("name", "")
            if name:
                schema["properties"][name] = getattr(attr, "type", "string")

        self._cache[cache_key] = schema
        return schema

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _smart_map_key(self, external_key: str, target_props: List[str],
                       threshold: float = 0.75) -> Optional[str]:
        """Heuristic key matching: exact → normalized → fuzzy."""
        if external_key in target_props:
            return external_key
        normalized_ext = re.sub(r'[_\s]+', '', external_key).lower()
        for prop in target_props:
            if re.sub(r'[_\s]+', '', prop).lower() == normalized_ext:
                return prop
        best_match, best_score = None, 0.0
        for prop in target_props:
            score = self._similarity(external_key, prop)
            if score > best_score and score >= threshold:
                best_score, best_match = score, prop
        return best_match

    def map_to_entity(
        self, raw_json: Dict[str, Any], domain_id: str, class_name: str,
        custom_mapping: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Map external JSON to an entity dict ready for GraphIndex."""
        schema = self._load_class_schema(domain_id, class_name)
        target_props = list(schema["properties"].keys())
        required = schema.get("required", [])
        mapped: Dict[str, Any] = {}
        used: set = set()

        custom = custom_mapping or {}
        for ek, tk in custom.items():
            if ek in raw_json:
                mapped[tk] = raw_json[ek]
                used.add(ek)

        for ek, v in raw_json.items():
            if ek in used:
                continue
            tk = self._smart_map_key(ek, target_props)
            if tk:
                mapped[tk] = v
                used.add(ek)
            else:
                mapped.setdefault("unmapped", {})[ek] = v

        # Fill missing required fields heuristically
        for req in required:
            if req not in mapped:
                if req == "name":
                    for k, v in raw_json.items():
                        if isinstance(v, str) and v.strip():
                            mapped["name"] = v.strip()
                            break

        eid = raw_json.get("id") or raw_json.get("uuid") or \
              f"ext_{domain_id}_{class_name}_{hash(str(raw_json)) % 1000000:06d}"
        return {
            "id": str(eid), "class": class_name, "domain": domain_id,
            "attributes": mapped, "source_raw": raw_json, "_mapper_version": "v1",
        }

    async def ingest_external(
        self, raw_json: Dict[str, Any], domain_id: str, class_name: str,
        custom_mapping: Optional[Dict[str, str]] = None,
        source_doc_id: str = "dynamic_mapper",
    ) -> Dict[str, Any]:
        """Map + write to GraphIndex in one call."""
        ed = self.map_to_entity(raw_json, domain_id, class_name, custom_mapping)
        g = GraphIndex.load(domain_id)

        existing = g._nodes.get(ed["id"])
        if existing:
            if existing.metadata:
                existing.metadata.update(ed["attributes"])
        else:
            g.add_entity(
                entity_id=ed["id"],
                entity_name=ed["attributes"].get("name", ed["id"]),
                class_name=class_name,
                source_doc_id=source_doc_id,
            )
            for key, value in ed["attributes"].items():
                g.add_entity_property(ed["id"], key, value)

        logger.info("Ingested external: %s (%s) → %s", ed["id"], class_name, domain_id)
        return ed
