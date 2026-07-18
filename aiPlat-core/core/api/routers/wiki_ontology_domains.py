"""
Wiki Domain Ontology CRUD API
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
import logging

router = APIRouter(tags=["wiki-ontology-domains"])

# ── Domain Ontology API (YAML-based) ─────────────────────────────

@router.get("/domains/{domain_id}/discover", response_model=Dict[str, Any])
async def discover_domain_assets(domain_id: str):
    """
    Agent discoverability API — returns all Object Types, Link Types, Action Types, 
    and Interfaces available in a domain. Agent can query this at runtime to discover
    what it can operate on, without pre-programmed tool descriptions.

    Response:
    {
      "objects": [{"name": "Customer", "label": "客户", "properties": [...], "implements": ["Diagnosable"]}],
      "links": [{"name": "places_order", "label": "下订单", "source": "Customer", "target": "Order"}],
      "actions": [<registered skills for this domain>],
      "interfaces": [{"name": "Diagnosable", "properties": [...], "implemented_by": [...]}]
    }
    """
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml, list_domain_files
    from core.harness.knowledge.ontology_loader import get_entities_by_interface, get_interface_definition
    from pathlib import Path as _Path
    import os as _os

    base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = base_dir / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    domain = load_ontology_from_yaml(str(file_path))

    # ── Object Types ──
    objects = []
    for cls in domain.classes:
        obj = {
            "name": cls.uri.split("/")[-1], "label": cls.label,
            "description": cls.description,
            "required_fields": cls.required_fields,
            "optional_fields": cls.optional_fields,
            "implements": cls.implements,
        }
        objects.append(obj)

    # ── Link Types ──
    links = []
    for prop in domain.object_properties:
        src = [d.split("/")[-1] for d in (prop.domain or [])]
        tgt = [r.split("/")[-1] for r in (prop.range or [])]
        links.append({
            "name": prop.uri.split("/")[-1], "label": prop.label,
            "source_types": src, "target_types": tgt,
        })

    # ── Interfaces ──
    interfaces = []
    for iface in domain.interfaces:
        impls = get_entities_by_interface(domain_id, iface.name)
        interfaces.append({
            "name": iface.name, "label": iface.label,
            "properties": iface.properties,
            "implemented_by": impls, "count": len(impls),
        })

    # ── Actions (Skills registered in this domain) ──
    actions = []
    try:
        from core.apps.skills.registry import SkillRegistry
        registry = SkillRegistry()
        for skill_id in registry.list_ids():
            skill = registry.get(skill_id)
            if skill:
                cfg = skill.get_config()
                actions.append({
                    "name": cfg.name, "description": cfg.description or "",
                    "input_schema": getattr(cfg, "input_schema", {}),
                    "submission_criteria": getattr(cfg, "submission_criteria", []),
                    "permissions": getattr(cfg, "permissions", None),
                })
    except Exception:
        pass

    return {
        "domain_id": domain_id, "domain_name": domain.name,
        "objects": objects, "links": links,
        "interfaces": interfaces, "actions": actions,
        "total_objects": len(objects), "total_links": len(links),
        "total_interfaces": len(interfaces), "total_actions": len(actions),
    }


@router.get("/domains/{domain_id}/interfaces", response_model=Dict[str, Any])
async def get_domain_interfaces(domain_id: str):
    """Return all Interface definitions and their implementations in a domain."""
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml, list_domain_files
    from pathlib import Path as _Path
    import os as _os
    base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = base_dir / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    domain = load_ontology_from_yaml(str(file_path))
    interfaces = []
    for iface in domain.interfaces:
        impls = [cls.label or cls.uri.split("/")[-1] for cls in domain.classes if iface.name in cls.implements]
        interfaces.append({"name": iface.name, "label": iface.label,
                          "description": iface.description, "properties": iface.properties,
                          "implemented_by": impls, "count": len(impls)})
    return {"domain_id": domain_id, "interfaces": interfaces, "total": len(interfaces)}


@router.post("/domains/save", response_model=Dict[str, Any])
async def save_ontology_domain(domain_id: str = "", yaml_content: str = ""):
    """Save a validated ontology YAML to disk (auto-aligns name with domain_id)."""
    if not domain_id or not yaml_content:
        raise HTTPException(status_code=400, detail="domain_id and yaml_content are required")
    try:
        from core.harness.knowledge.ontology_loader import validate_ontology_yaml, save_domain_yaml
        validation = validate_ontology_yaml(yaml_content)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=f"Validation failed: {validation['errors']}")
        dest_path = save_domain_yaml(domain_id, yaml_content)
        return {"saved": True, "path": dest_path, "domain_id": domain_id,
                "classes_n": validation["classes_n"], "properties_n": validation["properties_n"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/domains", response_model=Dict[str, Any])
async def list_ontology_domains():
    """List available domain ontology files."""
    from core.harness.knowledge.ontology_loader import list_domain_files, load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os

    base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    router = DomainRouter()
    domains = []
    for domain_id in list_domain_files():
        file_path = str(base_dir / f"{domain_id}.yaml")
        try:
            domain = load_ontology_from_yaml(file_path)
            cfg = router.domain_config(domain.id)
            domains.append({
                "id": domain.id,
                "name": domain.name,
                "version": domain.version,
                "description": domain.description,
                "namespace": domain.namespace,
                "class_count": len(domain.classes),
                "property_count": len(domain.object_properties) + len(domain.data_properties),
                "min_wiki_score": cfg.get("min_wiki_score", 0.25),
                "expand_subclasses": cfg.get("expand_subclasses", True),
                "min_cross_results": cfg.get("min_cross_results", 3),
                "system_prompt_id": cfg.get("system_prompt_id", ""),
                "collection_id": cfg.get("collection_id", domain.id),
            })
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    return {"domains": domains, "total": len(domains)}


@router.get("/domains/{domain_id}", response_model=Dict[str, Any])
async def get_ontology_domain(domain_id: str):
    """Get full domain ontology including classes + properties."""
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os

    base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = base_dir / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain ontology '{domain_id}' not found")
    try:
        domain = load_ontology_from_yaml(str(file_path))
        cfg = DomainRouter().domain_config(domain.id)
        return {
            "id": domain.id,
            "name": domain.name,
            "namespace": domain.namespace,
            "description": domain.description,
            "version": domain.version,
            "min_wiki_score": cfg.get("min_wiki_score", 0.25),
            "expand_subclasses": cfg.get("expand_subclasses", True),
            "min_cross_results": cfg.get("min_cross_results", 3),
            "system_prompt_id": cfg.get("system_prompt_id", ""),
            "collection_id": cfg.get("collection_id", domain.id),
            "classes": [{
                "uri": c.uri, "label": c.label,
                "parent": c.parent.replace(domain.namespace, "") if c.parent else None,
                "required_fields": c.required_fields,
                "optional_fields": c.optional_fields,
                "categories": c.allowed_categories,
                "description": c.description,
                "fields": c.fields,
                "states": getattr(c, "states", None) or None,
                "transitions": getattr(c, "transitions", None) or [],
                "side_effects": getattr(c, "side_effects", None) or [],
                "synonyms": getattr(c, "synonyms", None) or [],
            } for c in domain.classes],
            "object_properties": [{
                "uri": p.uri, "label": p.label,
                "domain": [d.replace(domain.namespace, "") for d in (p.domain or [])],
                "range": [r.replace(domain.namespace, "") for r in (p.range or [])],
                "transitive": p.is_transitive, "symmetric": p.is_symmetric,
                "description": getattr(p, "description", "") or "",
            } for p in domain.object_properties],
            "data_properties": [{
                "uri": p.uri, "label": p.label,
                "domain": [d.replace(domain.namespace, "") for d in (p.domain or [])],
                "range": p.range,
            } for p in domain.data_properties],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load domain '{domain_id}': {e}")


@router.get("/domains/{domain_id}/validation-report", response_model=Dict[str, Any])
async def validate_ontology_domain(domain_id: str, collection: str = ""):
    """Cross-check existing data (Wiki pages + Graph nodes) against current ontology schema.

    Returns validation report with orphan pages, missing required fields,
    orphan graph nodes, and state mismatches.
    """
    from core.harness.knowledge.ontology_validator import validate_domain, validate_report_to_dict
    cid = collection or domain_id
    report = validate_domain(domain_id, collection_id=cid)
    return validate_report_to_dict(report)


_verify_cache: dict = {}  # domain_id → (timestamp, result)


@router.post("/domains/{domain_id}/verify", response_model=Dict[str, Any])
async def verify_ontology_domain(domain_id: str, collection: str = ""):
    """Unified verification: classification coverage + graph stats + anomalies.
    
    Results cached for 60s to reduce filesystem scan load.
    """
    import time as _time
    now = _time.time()
    cached = _verify_cache.get(domain_id)
    if cached and now - cached[0] < 60:
        return cached[1]

    from core.harness.knowledge.wiki_engine import search_pages, list_all_pages
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.knowledge.domain_router import DomainRouter
    from collections import Counter

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    # 1. Classification coverage
    all_pages = list_all_pages(collection_id=cid)
    cat_counts = Counter()
    unclassified = 0
    for p in all_pages:
        cat = str(p.get("category") or "")
        if cat in ("entities", "topics", ""):
            unclassified += 1
        else:
            cat_counts[cat] += 1

    # 2. Graph stats
    graph_nodes = graph_edges = 0
    try:
        graph = GraphIndex.load(domain_id)
        graph_nodes = len(graph._nodes)
        graph_edges = sum(len(n.out_edges) for n in graph._nodes.values())
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # 3. Issues detection
    issues = []
    total = len(all_pages)

    if unclassified > total * 0.5:
        issues.append({"type": "unclassified_high", "severity": "warn",
                       "detail": f"{unclassified}/{total} 页未分类，执行分类+构建"})
    elif unclassified > 0:
        issues.append({"type": "unclassified", "severity": "info",
                       "detail": f"{unclassified}/{total} 页未分类"})

    if graph_nodes < total * 0.1:
        issues.append({"type": "few_nodes", "severity": "warn",
                       "detail": f"图节点 {graph_nodes}，远少于 {total} 页"})

    classified_by_cat = {c: n for c, n in cat_counts.items() if n > 0}
    if len(classified_by_cat) >= 3 and graph_edges == 0:
        issues.append({"type": "no_edges", "severity": "warn",
                       "detail": "分类多但图中无边，运行构建实例"})

    overall = "pass" if not any(i["severity"] == "warn" for i in issues) else "warn"

    result = {
        "overall": overall, "domain_id": domain_id,
        "classification": {"total_pages": total, "classified": total - unclassified,
                          "unclassified": unclassified, "by_category": dict(cat_counts.most_common(10))},
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "issues": issues,
    }
    _verify_cache[domain_id] = (now, result)
    return result


@router.get("/domains/{domain_id}/scoring", response_model=Dict[str, Any])
async def get_scoring_config(domain_id: str):
    """Get current retrieval scoring weights for a domain."""
    try:
        import yaml, os
        from pathlib import Path as _Path
        config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
            str(_Path(__file__).resolve().parent.parent.parent.parent.parent /
                "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))
        with open(config_path) as f:
            profile = yaml.safe_load(f) or {}
        return profile.get("retrieval_scoring", {
            "semantic": 0.55, "fts_keyword": 0.15,
            "freshness": 0.10, "credibility": 0.10, "density": 0.10,
        })
    except Exception:
        return {"semantic": 0.55, "fts_keyword": 0.15, "freshness": 0.10, "credibility": 0.10, "density": 0.10}


@router.put("/domains/{domain_id}/scoring", response_model=Dict[str, Any])
async def update_scoring_config(domain_id: str, config: dict):
    """Update retrieval scoring weights. Changes take effect immediately."""
    import yaml, os
    from pathlib import Path as _Path
    config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
        str(_Path(__file__).resolve().parent.parent.parent.parent.parent /
            "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))
    try:
        with open(config_path) as f:
            profile = yaml.safe_load(f) or {}
    except Exception:
        profile = {}
    allowed = {"semantic", "fts_keyword", "freshness", "credibility", "density"}
    scoring = {k: float(config.get(k, 0.10)) for k in allowed}
    profile["retrieval_scoring"] = scoring
    with open(config_path, "w") as f:
        yaml.dump(profile, f, allow_unicode=True, default_flow_style=False)
    # Clear verify cache so next verify reflects new weights
    _verify_cache.pop(domain_id, None)
    return {"status": "saved", "scoring": scoring, "cache_cleared": True}


def _clean_summary(text: str, max_len: int = 200) -> str:
    """Strip markdown images, HTML tags, and truncate for clean display."""
    import re as _re
    # Strip markdown images: ![alt](url)
    text = _re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # Strip raw image URLs
    text = _re.sub(r'https?://\S+\.(?:jpg|jpeg|png|gif|webp|gif)\S*', '', text)
    # Strip HTML tags
    text = _re.sub(r'<[^>]+>', '', text)
    # Collapse whitespace
    text = _re.sub(r'\s+', ' ', text).strip()
    # Remove leading special chars
    text = _re.sub(r'^[`\s]+', '', text)
    return text[:max_len]


@router.get("/domains/{domain_id}/instances", response_model=Dict[str, Any])
async def list_instances_by_class(domain_id: str, class_label: str = ""):
    """List all ontology instances (Wiki pages) for a given class_label.

    Maps class_label → domain YAML categories → searches Wiki pages by category.
    Wiki pages ARE the ontology instances — no separate graph node store needed.
    """
    from core.harness.knowledge.wiki_engine import search_pages, read_page
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os, re as _re

    if not class_label:
        return {"instances": [], "total": 0, "error": "class_label parameter required"}

    # Resolve class_label → category names
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    categories = []
    if onto_path.exists():
        domain = load_ontology_from_yaml(str(onto_path))
        for cls in domain.classes:
            if cls.label == class_label:
                categories = cls.allowed_categories or []
                break

    if not categories:
        # Fallback: use class_label itself as category
        categories = [class_label]

    router = DomainRouter()
    cid = router.resolve_collection(domain_id) or domain_id

    instances = []
    for cat in categories:
        pages = search_pages(category=cat, limit=200, collection_id=cid)
        for p in pages:
            summary = _clean_summary(p.get("summary", "") or "")
            if not summary:
                try:
                    full = read_page(p.get("title", ""), category=cat, collection_id=cid)
                    if full:
                        body = str(full.get("body", "") or "")[:500]
                        body = _re.sub(r'[#*`>\[\]!|~]', '', body)
                        body = _re.sub(r'https?://\S+', '', body)
                        body = _re.sub(r'\s+', ' ', body).strip()
                        summary = body[:200]
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

            instances.append({
                "entity_name": p.get("title", ""),
                "wiki_title": p.get("title", ""),
                "class_name": class_label,
                "category": cat,
                "summary": _clean_summary(p.get("summary", "") or ""),
                "tags": p.get("tags", []) or [],
                "related": p.get("related", []) or [],
                "state": p.get("frontmatter", {}).get("state", "") if isinstance(p.get("frontmatter"), dict) else "",
                "last_updated": p.get("last_updated", ""),
            })

    return {"instances": instances, "total": len(instances), "class_label": class_label}




@router.get("/class-by-category", response_model=Dict[str, Any])
async def get_ontology_class_by_category(category: str = "entities", collection: str = "default"):
    """Return the OntologyClass matching a category name, with required/optional/template fields.
    
    Used by Wiki creation form to dynamically render fields.
    Checks all loaded domain ontologies + built-in classes.
    """
    from core.harness.knowledge.ontology_loader import load_all_domains
    from core.harness.knowledge.knowledge_ontology import CLASSES
    from pathlib import Path as _Path
    import os as _os

    result = {"category": category, "found": False, "required_fields": [], "optional_fields": [],
              "template_markdown": "", "class_label": category}

    # 1) Check domain ontologies first
    domains = load_all_domains()
    for domain_id, domain in domains.items():
        for cls in domain.classes:
            if category in cls.allowed_categories:
                result.update({
                    "found": True,
                    "domain": domain_id,
                    "required_fields": cls.required_fields,
                    "optional_fields": cls.optional_fields,
                    "template_markdown": cls.template_markdown,
                    "class_label": cls.label,
                    "class_uri": cls.uri,
                })
                return result

    # 2) Fall back to built-in CLASSES
    for cls in CLASSES:
        if category in (cls.allowed_categories or []):
            result.update({
                "found": True,
                "domain": "built-in",
                "required_fields": cls.required_fields,
                "optional_fields": cls.optional_fields,
                "template_markdown": cls.template_markdown,
                "class_label": cls.label,
                "class_uri": cls.uri,
            })
            return result

    return result


@router.post("/domains/{domain_id}/classify-all", response_model=Dict[str, Any])
async def classify_all_pages(domain_id: str, collection: str = "", limit: int = 5):
    """Auto-classify unclassified wiki pages using LLM (reads body content), then auto-trigger build-instances.

    Reads first 300 chars of each page body to improve classification accuracy.
    After classification, auto-calls build-instances to populate the knowledge graph.
    """
    from core.harness.knowledge.wiki_engine import search_pages, read_page, write_page
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from core.harness.utils.model_injection import create_selected_adapter
    from core.adapters.llm.base import LLMConfig
    import re as _re, json as _json, os as _os, logging
    from pathlib import Path as _Path

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    all_pages = search_pages(limit=200, collection_id=cid)
    batch = [p for p in all_pages if p.get('category') in ('entities', 'topics', '')][:limit]
    if not batch:
        return {"status": "no_unclassified", "total_pages": len(all_pages)}

    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    all_classes = []
    if onto_path.exists():
        domain = load_ontology_from_yaml(str(onto_path))
        for cls in domain.classes:
            all_classes.append({"label": cls.label, "categories": cls.allowed_categories or []})

    if not all_classes:
        return {"status": "no_classes", "total_pages": len(batch)}

    # Pre-read page bodies for better classification
    page_bodies = {}
    for p in batch[:5]:  # Limit to 15 per LLM call
        try:
            full = read_page(p["title"], collection_id=cid)
            if full:
                page_bodies[p["title"]] = str(full.get("body", "") or "")[:100]
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    cat_names = ", ".join(c["categories"][0] for c in all_classes if c["categories"])
    class_lines = "\n".join(
        f"  - {c['label']}: category='{c['categories'][0] if c['categories'] else 'none'}'"
        for c in all_classes
    )
    page_lines = "\n".join(
        f"  - {p['title']}\n    excerpt: {page_bodies.get(p['title'], '')[:120]}"
        for p in batch[:15]
    )

    prompt = (
        f"Classify each page. Use ONLY: {cat_names}\n\n"
        f"Pages:\n{page_lines}\n\n"
        f"Output JSON array. Include the EXACT page title (copy-paste from above) and category:\n"
        f'[{{"title":"copy the exact title from the list above","category":"one of {cat_names}"}}]'
    )

    try:
        from core.harness.utils.model_injection import generate_with_fallback
        data = {"suggestions": []}

        for attempt in range(5):
            resp, _ = await generate_with_fallback(
                "ontology_gen",
                [{"role": "system", "content": "Output ONLY valid JSON without markdown."},
                 {"role": "user", "content": prompt}],
                timeout=120, config=LLMConfig(model="", timeout=120, max_tokens=2048),
            )
            content = resp.content if hasattr(resp, 'content') else str(resp)
            logging.getLogger("wiki").info(f"classify-all response: {content[:200]}")
            clean = content.strip()
            # Strip markdown code fences
            if clean.startswith('```'):
                clean = _re.sub(r'^```\w*\s*', '', clean)
                clean = _re.sub(r'\s*```$', '', clean)
            # Support both object {...} and array [{...}] responses
            brace_start = clean.find('{')
            bracket_start = clean.find('[')
            start = bracket_start if bracket_start >= 0 and (brace_start < 0 or bracket_start < brace_start) else brace_start
            if start >= 0:
                dec = _json.JSONDecoder()
                data, _ = dec.raw_decode(clean[start:])
                if isinstance(data, list):
                    data = {"suggestions": data}
                elif isinstance(data, dict):
                    if "suggestions" not in data and "pages" not in data and "title" in data:
                        data = {"suggestions": [data]}
                data_sug = data.get("suggestions") or data.get("pages") or []
                if isinstance(data_sug, list) and len(data_sug) > 0:
                    break
    except Exception as e:
        logging.getLogger("wiki").warning(f"classify-all LLM failed: {e}")
        return {"status": "llm_failed", "total": len(batch), "error": str(e)}

    suggestions = data.get("suggestions", []) or data.get("pages", [])
    valid_cats = set()
    for c in all_classes:
        valid_cats.update(c.get("categories", []) or [])
    applied, errors = [], []

    # Normalize function for title matching
    def _norm(t: str) -> str:
        t = t.strip()
        t = __import__('re').sub(r'[：:—\-–\s、，。；！？【】（）《》""'']+', '', t)
        return __import__('unicodedata').normalize('NFKC', t)[:80]

    # Build normalized title → page mapping for batch
    page_by_norm = {}
    for p in batch:
        page_by_norm[_norm(p.get("title", ""))] = p

    # Apply each suggestion
    for si, s in enumerate(suggestions):
        if isinstance(s, str):
            continue  # skip malformed LLM output
        s_title = s.get("title", "")
        # Strip [category] prefix that LLM may copy from prompt
        s_title = _re.sub(r'^\[[^\]]+\]\s*', '', s_title).strip()
        s_cat = s.get("category", "")
        # Fallback: if title missing, match by position in batch
        if not s_title and si < len(batch):
            s_title = batch[si].get("title", "")
        if s_cat not in valid_cats:
            continue  # skip hallucinated categories

        # Find matching page by normalized title
        nt = _norm(s_title)
        page = page_by_norm.get(nt)
        if not page:
            # Try partial match
            for pn, pp in page_by_norm.items():
                if pn and nt and (pn in nt or nt in pn):
                    page = pp; break
        if not page:
            continue

        title = page.get("title", "")
        if s_cat == page.get("category"):
            continue

        try:
            full = read_page(title, collection_id=cid)
            if not full: continue
            write_page(title=title, body=full.get("body", ""),
                       category=s_cat, collection_id=cid,
                       tags=list(full.get("tags", []) or []))
            applied.append({"title": title, "category": s_cat,
                           "confidence": s.get("confidence", 0)})
        except Exception as e:
            errors.append(f"{title}: {e}")

    return {
        "status": "classified", "total_pages": len(batch),
        "applied": len(applied), "errors": len(errors), "details": applied[:20],
        "error_details": errors[:10],
    }
