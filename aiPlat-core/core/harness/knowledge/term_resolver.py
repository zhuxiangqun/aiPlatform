u"""
Term Resolver — 跨域术语消歧引擎 (v2.6).

扫描所有 domain YAML 中的 class labels + field names，
检测同名异义（same label, different domain）和同义异名（different label, similar meaning）。
消歧结果注入到 DomainRouter 分类和 Agent 上下文。

数据存储: ~/.aiplat/terms/ambiguities.json
"""
from __future__ import annotations

import json as _json
import logging
import os as _os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("term_resolver")

_TERMS_DIR = _os.path.expanduser("~/.aiplat/terms")


def _ensure_dir() -> Path:
    p = Path(_TERMS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def scan_ambiguities(ontologies_dir: str = "") -> Dict[str, List[Dict[str, Any]]]:
    u"""扫描所有域 YAML，检测术语歧义。

    Returns:
        {
            "same_name_different_domain": [
                {"label": "客户", "domains": {"sales": "...", "delivery": "..."}, ...},
            ],
            "similar_label_different_name": [
                {"labels": ["采购合同", "供货合同"], "domains": {...}, "similarity": 0.88},
            ],
        }
    """
    base = _os.path.expanduser(ontologies_dir or _os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
    base_path = Path(base)
    if not base_path.exists():
        return {"same_name_different_domain": [], "similar_label_different_name": []}

    import yaml

    label_domain_map: Dict[str, List[Tuple[str, str, str]]] = {}
    all_labels: Dict[str, str] = {}

    for yaml_file in sorted(base_path.glob("*.yaml")):
        domain_id = yaml_file.stem
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not raw or not isinstance(raw, dict):
            continue

        classes = raw.get("classes", {})
        if isinstance(classes, dict):
            for cls_name, cls_def in classes.items():
                label = cls_def.get("label", cls_name)
                class_desc = cls_def.get("description", "")
                label_domain_map.setdefault(label, []).append((domain_id, cls_name, class_desc))
                all_labels[f"{domain_id}:{label}"] = class_desc

    same_name: List[Dict[str, Any]] = []
    for label, entries in label_domain_map.items():
        if len(entries) > 1:
            domains = {}
            for dom_id, cls_name, desc in entries:
                domains[dom_id] = {"class_name": cls_name, "description": desc[:200]}
            same_name.append({"label": label, "domains": domains, "count": len(entries)})

    similar_label: List[Dict[str, Any]] = []
    try:
        from core.harness.infrastructure.infra_embedding_adapter import create_infra_embedding_adapter
        adapter = create_infra_embedding_adapter()
        label_items = list(all_labels.items())
        embeddings = {}
        for key, desc in label_items:
            text = f"{key}: {desc}" if desc else key
            embedding = adapter.encode(text)
            if embedding is not None and len(embedding) > 0:
                embeddings[key] = embedding

        import numpy as np
        keys = list(embeddings.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                vec_i = np.array(embeddings[keys[i]])
                vec_j = np.array(embeddings[keys[j]])
                sim = float(np.dot(vec_i, vec_j) / (np.linalg.norm(vec_i) * np.linalg.norm(vec_j) + 1e-8))
                if sim > 0.85:
                    dom_i = keys[i].split(":", 1)[0]
                    dom_j = keys[j].split(":", 1)[0]
                    if dom_i != dom_j:
                        label_i = keys[i].split(":", 1)[1]
                        label_j = keys[j].split(":", 1)[1]
                        similar_label.append({
                            "labels": [label_i, label_j],
                            "domains": {dom_i: label_i, dom_j: label_j},
                            "similarity": round(sim, 4),
                        })
    except Exception as e:
        logger.debug("Embedding-based synonym detection skipped: %s", e)

    return {
        "same_name_different_domain": same_name,
        "similar_label_different_name": similar_label[:50],
    }


def resolve_term(term: str, *, domain_id: str = "", ontologies_dir: str = "") -> Dict[str, Any]:
    u"""查询某术语在所有域的消歧信息。

    Returns:
        {
            "term": "...",
            "matches": [{"domain_id": "...", "class_name": "...", "description": "...", "synonyms": [...]}],
            "same_name_ambiguity": bool,
            "suggested_domain": "..." or null,
        }
    """
    ambiguities = scan_ambiguities(ontologies_dir)
    matches: List[Dict] = []
    is_ambiguous = False

    for entry in ambiguities.get("same_name_different_domain", []):
        if entry["label"] == term:
            is_ambiguous = True
            for dom, info in entry["domains"].items():
                matches.append({
                    "domain_id": dom,
                    "class_name": info["class_name"],
                    "description": info["description"],
                })

    if domain_id and not matches:
        base = Path(_os.path.expanduser(
            ontologies_dir or _os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies")
        ))
        yaml_file = base / f"{domain_id}.yaml"
        if yaml_file.exists():
            import yaml
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            classes = raw.get("classes", {}) if raw else {}
            for cls_name, cls_def in classes.items():
                if cls_def.get("label") == term or term in cls_def.get("synonyms", []):
                    matches.append({
                        "domain_id": domain_id,
                        "class_name": cls_name,
                        "description": cls_def.get("description", ""),
                        "synonyms": cls_def.get("synonyms", []),
                    })

    return {
        "term": term,
        "matches": matches,
        "same_name_ambiguity": is_ambiguous and len(matches) > 1,
        "suggested_domain": matches[0]["domain_id"] if matches else None,
    }


def persist_ambiguities(ontologies_dir: str = "") -> str:
    u"""扫描并持久化歧义结果到 ~/.aiplat/terms/ambiguities.json。"""
    result = scan_ambiguities(ontologies_dir)
    path = _ensure_dir() / "ambiguities.json"
    path.write_text(_json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Term ambiguities persisted: same_name=%d, similar_label=%d",
                 len(result["same_name_different_domain"]),
                 len(result["similar_label_different_name"]))
    return str(path)
