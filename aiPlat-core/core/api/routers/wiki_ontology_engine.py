"""Wiki Ontology Engine API — parsing, classification, resolution, synthesis"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
import logging
import re as _re
import os as _os
import time as _time
import json as _json
import asyncio

router = APIRouter(tags=["wiki-ontology-engine"])

@router.post("/engine/process", response_model=Dict[str, Any])
async def ontology_engine_process(req: dict, collection: str = "default"):
    """本体引擎处理：单文档 → 本体实例。
    
    请求体: {"text": "...", "domain_id": "ai-knowledge", "doc_id": "kb:xxx"}
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    text = req.get("text", "") if isinstance(req, dict) else ""
    doc_id = req.get("doc_id", "") if isinstance(req, dict) else ""

    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    from core.harness.ontology_engine.engine import load_engine
    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    chunks = [{"id": "chunk-0", "text": text, "entities": []}]
    result = await engine.process_chunks(chunks, doc_id=doc_id)
    return result.to_dict()


@router.post("/engine/process-and-write", response_model=Dict[str, Any])
async def ontology_engine_process_and_write(req: dict, collection: str = "default"):
    """本体引擎 → 实例 → 自动写 Wiki 页面。
    
    请求体: {"text": "...", "domain_id": "ai-knowledge", "doc_id": "kb:xxx", "auto_write": true}
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    text = req.get("text", "") if isinstance(req, dict) else ""
    doc_id = req.get("doc_id", "") if isinstance(req, dict) else ""
    auto_write = bool(req.get("auto_write", True)) if isinstance(req, dict) else True

    from core.harness.ontology_engine.engine import load_engine
    from core.harness.knowledge.wiki_engine import write_page

    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    chunks = [{"id": "chunk-0", "text": text, "entities": []}]
    result = await engine.process_chunks(chunks, doc_id=doc_id)

    written = []
    if auto_write and result.instances:
        for inst in result.instances:
            fm = inst.get("frontmatter", {})
            title = fm.get("title", "")
            if not title:
                continue
            try:
                await write_page(
                    title=title,
                    body=fm.get("body", "") or str(fm.get("description", "") or ""),
                    category=fm.get("category", "entities"),
                    collection_id=collection,
                    tags=list(fm.get("tags", []) or []),
                    summary=str(fm.get("summary", "") or ""),
                )
                written.append(title)
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    return {**result.to_dict(), "written_pages": written, "written_count": len(written)}


@router.post("/domains/{domain_id}/cleanup-nodes", response_model=Dict[str, Any])
async def cleanup_cross_domain_nodes(domain_id: str):
    """Remove graph nodes whose entity_name matches keywords from other domains.

    Auto-detects cross-domain vocabulary from other domains' YAML labels and synonyms.
    Config-driven — no hardcoded domain terms. Scales to any new domain.
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml, load_all_domains
    from pathlib import Path as _Path
    import os as _os

    graph = GraphIndex.load(domain_id)

    # Build current domain's vocabulary from labels + synonyms
    domain_vocab = set()
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if onto_path.exists():
        domain = load_ontology_from_yaml(str(onto_path))
        for cls in domain.classes:
            domain_vocab.add(cls.label)
            for syn in (getattr(cls, "synonyms", []) or []):
                domain_vocab.add(syn)

    # Auto-build cross-domain keywords from OTHER domains' labels + synonyms
    cross_keywords = set()
    try:
        for other_id, other_dom in load_all_domains().items():
            if other_id == domain_id:
                continue
            for cls in other_dom.classes:
                cross_keywords.add(cls.label)
                for syn in (getattr(cls, "synonyms", []) or []):
                    cross_keywords.add(syn)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    if not cross_keywords:
        return {"status": "no_cross_keywords", "domain_id": domain_id}

    removed = []
    for node in list(graph._nodes.values()):
        name = node.entity_name or ""
        if any(kw in name for kw in cross_keywords) and not any(v in name for v in domain_vocab):
            graph.remove_entity(node.entity_id)
            removed.append({"entity_id": node.entity_id, "entity_name": name[:80], "class_name": node.class_name})

    return {"status": "cleaned", "domain_id": domain_id, "removed": len(removed), "details": removed[:20]}


@router.post("/domains/{domain_id}/backfill-summaries", response_model=Dict[str, Any])
async def backfill_summaries(domain_id: str, collection: str = "", limit: int = 200):
    """Backfill empty summaries for all wiki pages in this domain's collection.

    Calls write_page for each page with empty summary, which triggers
    auto-summary generation from the page body.
    """
    from core.harness.knowledge.wiki_engine import read_page, write_page, list_all_pages
    from core.harness.knowledge.domain_router import DomainRouter

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    pages = list_all_pages(collection_id=cid)
    filled = 0
    for page in pages[:limit]:
        title = str(page.get("title") or "")
        if not title:
            continue
        try:
            page_cat = str(page.get("category") or "entities")
            full = read_page(title, category=page_cat, collection_id=cid)
            if not full:
                continue
            body = str(full.get("body", "") or "")
            write_page(
                title=title, body=body,
                category=str(full.get("category", "entities")),
                collection_id=cid, summary="",  # empty → auto-generate from body
                tags=list(full.get("tags", []) or []),
            )
            filled += 1
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    return {"status": "backfilled", "filled": filled, "total": min(len(pages), limit)}


_build_semaphore = None  # lazy init to avoid import-time asyncio issues


@router.post("/domains/{domain_id}/build-instances", response_model=Dict[str, Any])
async def build_instances_batch(domain_id: str, collection: str = "", limit: int = 50):
    """Batch-run ontology engine on all Wiki pages in this domain's collection.
    
    Uses parallel processing (2 concurrent) — prevents OOM on 16GB machines.
    """
    from core.harness.ontology_engine.engine import load_engine
    from core.harness.knowledge.wiki_engine import read_page, write_page, list_all_pages
    from core.harness.knowledge.domain_router import DomainRouter
    import asyncio

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    # ── Differential: skip already-built pages ──
    import os as _os, json as _json
    from pathlib import Path as _Path
    built_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "graph" / f"{domain_id}_built.json"
    built_pages = set()
    if built_path.exists():
        try:
            built_pages = set(_json.loads(built_path.read_text(encoding="utf-8")))
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    pages = list_all_pages(collection_id=cid)
    if not pages:
        return {"status": "no_pages", "domain_id": domain_id, "collection": cid}

    # Filter to classified pages only, skip already-built
    valid = []
    new_sources = []
    skipped = 0
    for page in pages[:limit]:
        cat = str(page.get("category") or "")
        if cat in ("entities", "topics", ""):
            continue
        title = str(page.get("title") or "")
        if title in built_pages:
            skipped += 1
            continue
        full = read_page(title, category=str(page.get("category") or "entities"), collection_id=cid)
        if full and len(str(full.get("body") or "")) >= 20:
            valid.append({"title": title, "body": str(full.get("body") or "")[:8000]})
            new_sources.append(title)

    results = {"domain_id": domain_id, "collection": cid, "total_pages": len(pages),
               "processed": 0, "instances_created": 0, "errors": 0, "details": []}

    # Parallel batch processing: 10 concurrent pages
    batch_size = 2  # was 10 — reduced to prevent OOM on M2 16GB
    for i in range(0, len(valid), batch_size):
        batch = valid[i:i + batch_size]
        tasks = [_process_single_page(engine, page, cid) for page in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, br in enumerate(batch_results):
            if isinstance(br, Exception):
                results["errors"] += 1
                results["details"].append({"title": batch[j]["title"], "error": str(br)})
            else:
                results["processed"] += 1
                results["instances_created"] += br.get("instances", 0)
                results["details"].append(br)
                # Mark page as built
                built_pages.add(new_sources[i + j])

    # Persist differential tracking
    results["skipped"] = skipped
    if new_sources:
        built_path.parent.mkdir(parents=True, exist_ok=True)
        built_path.write_text(_json.dumps(sorted(built_pages), ensure_ascii=False), encoding="utf-8")

    return results


@router.post("/domains/{domain_id}/build-edges", response_model=Dict[str, Any])
async def build_cross_page_edges(domain_id: str):
    """Build cross-page edges by linking graph nodes via wiki references + keyword overlap.
    
    Strategy:
      1. Load graph nodes + wiki page cross-references (related, source_articles)
      2. Match references to other graph nodes
      3. Use YAML relation type definitions to determine edge type
      4. Add edges to graph via add_relation()
    """
    from core.harness.ontology_engine.engine import get_graph
    from core.harness.knowledge.wiki_engine import read_page, list_all_pages
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os

    graph = get_graph(domain_id)
    if not graph or len(graph._nodes) < 2:
        return {"edges_created": 0, "message": "Not enough nodes for cross-page edges"}

    router = DomainRouter()
    cid = router.resolve_collection(domain_id) or domain_id
    nodes = list(graph._nodes.values())

    # Load domain relation type definitions
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    domain = load_ontology_from_yaml(str(onto_path))
    class_to_categories = {}
    for cls in domain.classes:
        class_to_categories[cls.label] = set(cls.allowed_categories or [])

    # Build: entity_name → node + wiki page data
    name_to_node = {}
    name_to_page = {}
    all_pages = list_all_pages(collection_id=cid)
    page_by_title = {p.get("title", ""): p for p in all_pages}

    for node in nodes:
        name = node.entity_name or node.entity_id
        name_to_node[name] = node
        # Try to find matching wiki page
        for title, page in page_by_title.items():
            if name in title or title in name:
                name_to_page[name] = page
                break

    # Reload pages for nodes that need cross-reference data
    node_cross_refs = {}
    for name, page in name_to_page.items():
        full = read_page(page.get("title", ""), category=page.get("category", "entities"), collection_id=cid)
        if full:
            related = full.get("related", []) or []
            sources = full.get("source_articles", []) or []
            body = full.get("body", "")
            # Extract wiki-style links from body [[title]]
            import re
            wiki_links = re.findall(r'\[\[([^\]]+)\]\]', str(body))
            node_cross_refs[name] = {
                "related": [str(r) for r in related],
                "sources": [str(s) for s in sources],
                "body": str(body)[:2000],
                "wiki_links": wiki_links,
            }

    # Phase 1: Match via wiki references (related, source_articles, [[links]])
    edges_added = 0
    seen_pairs = set()
    existing_edges = set()
    for node in nodes:
        nid = node.entity_id or node.entity_name
        if nid not in graph._nodes:
            continue
        for edge in graph._nodes[nid].out_edges:
            existing_edges.add((nid, edge.target_id))

    for name, refs in node_cross_refs.items():
        if name not in name_to_node:
            continue
        source_node = name_to_node[name]
        source_id = source_node.entity_id or name
        source_class = source_node.class_name or ""

        # Collect all reference targets
        ref_targets = []
        ref_targets.extend(refs.get("related", []))
        ref_targets.extend(refs.get("sources", []))
        ref_targets.extend(refs.get("wiki_links", []))

        for ref in ref_targets:
            ref = str(ref).strip()
            if not ref:
                continue
            # Match to node by name
            for target_name, target_node in name_to_node.items():
                if target_name == name:
                    continue  # skip self
                target_id = target_node.entity_id or target_name
                target_class = target_node.class_name or ""
                pair_key = (source_id, target_id)
                if pair_key in seen_pairs:
                    continue
                if pair_key in existing_edges:
                    continue
                # Check if ref matches target
                ref_low = ref.lower()
                target_low = target_name.lower()
                if ref_low not in target_low and target_low not in ref_low:
                    continue
                seen_pairs.add(pair_key)

                # Determine relation type from YAML object_properties
                rel_type = _match_relation_type(domain, source_class, target_class)
                if rel_type:
                    graph.add_relation(
                        source_id=source_id,
                        target_id=target_id,
                        relation_name=rel_type,
                        confidence=0.8,
                    )
                    edges_added += 1

    # Phase 2: Entity name in body — primary cross-page linking strategy
    for name_a, refs_a in node_cross_refs.items():
        if name_a not in name_to_node:
            continue
        source_node = name_to_node[name_a]
        source_id = source_node.entity_id or name_a
        source_class = source_node.class_name or ""

        for name_b, refs_b in node_cross_refs.items():
            if name_b == name_a:
                continue
            pair_key = (source_id, name_b)
            if pair_key in seen_pairs or pair_key in existing_edges:
                continue
            target_node = name_to_node.get(name_b)
            if not target_node:
                continue
            target_id = target_node.entity_id or name_b
            target_class = target_node.class_name or ""

            body_a = refs_a.get("body", "")
            body_b = refs_b.get("body", "")

            # Check bidirectional keyword overlap
            linked = False
            # name_a appears in body_b?
            if name_a and len(name_a) >= 3 and name_a.lower() in body_b.lower():
                linked = True
            # name_b appears in body_a?
            elif name_b and len(name_b) >= 3 and name_b.lower() in body_a.lower():
                linked = True
            # Overlap in page names (one title contains the other)
            elif name_a and name_b and (name_a.lower() in name_b.lower() or name_b.lower() in name_a.lower()):
                linked = True

            if not linked:
                continue

            # ── Semantic gate: keyword overlap ≥ 2 + cosine ≥ 0.7 ──
            keywords_a = _extract_keywords_light(body_a) if body_a else set()
            keywords_b = _extract_keywords_light(body_b) if body_b else set()
            overlap = len(keywords_a & keywords_b)
            if overlap < 2:
                continue  # weak candidate, skip

            # Read cached vectors from vectors.json (no recomputation)
            vec_a = _get_cached_vector(name_a, collection_id=cid)
            vec_b = _get_cached_vector(name_b, collection_id=cid)
            if vec_a and vec_b:
                sim = _cosine_similarity(vec_a, vec_b)
                if sim < 0.7:
                    continue  # semantically unrelated

            seen_pairs.add(pair_key)

            rel_type = _match_relation_type(domain, source_class, target_class)
            if not rel_type:
                rel_type = _match_relation_type(domain, target_class, source_class)
                source_id, target_id = target_id, source_id  # swap for inverse

            if rel_type:
                graph.add_relation(
                    source_id=source_id,
                    target_id=target_id,
                    relation_name=rel_type,
                    confidence=0.6,
                )
                edges_added += 1

    graph.save()
    return {"edges_created": edges_added, "total_nodes": len(nodes),
            "total_pairs_checked": len(seen_pairs)}


def _extract_keywords_light(text: str) -> set:
    """Extract Chinese bigrams + English words as keyword set."""
    import re
    tokens = set()
    # Chinese: 2-gram sliding window
    chinese = re.findall(r'[\u4e00-\u9fff]+', text)
    for seg in chinese:
        for i in range(len(seg) - 1):
            tokens.add(seg[i:i+2])
    # English: words ≥ 3 chars
    eng = re.findall(r'[a-zA-Z]{3,}', text)
    tokens.update(w.lower() for w in eng)
    return tokens


def _get_cached_vector(title: str, *, collection_id: str = "default") -> list:
    """Read cached embedding vector from vectors.json. Returns None if not found."""
    import json, os
    from pathlib import Path
    cache_path = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")) / "wiki" / "collections" / collection_id / "vectors.json"
    if not cache_path.exists():
        return None
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        return cache.get(title)
    except Exception:
        return None


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two float lists."""
    import math
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _match_relation_type(domain, source_class: str, target_class: str) -> str:
    """Find matching relation type from domain YAML object_properties.
    
    Resolves both Chinese labels and short IDs to match against full URI domain/range values.
    """
    # Build label→uri mapping
    label_to_uri = {}
    for cls in domain.classes:
        uri = getattr(cls, 'uri', '') or ''
        if uri:
            label_to_uri[cls.label] = uri
    
    # Candidate URIs for source and target
    source_uris = {source_class, label_to_uri.get(source_class, '')}
    target_uris = {target_class, label_to_uri.get(target_class, '')}
    
    for prop in (domain.object_properties or []):
        domains = set(prop.domain or [])
        ranges = set(prop.range or [])
        if source_uris & domains and target_uris & ranges:
            return prop.label
    # Try inverse
    for prop in (domain.object_properties or []):
        domains = set(prop.domain or [])
        ranges = set(prop.range or [])
        if target_uris & domains and source_uris & ranges:
            return prop.inverse_of or prop.inverse_label or ""
    return ""


async def _process_single_page(engine, page: dict, cid: str) -> dict:
    """Process one page through the engine pipeline. Runs in parallel with others."""
    import asyncio
    global _build_semaphore
    if _build_semaphore is None:
        _build_semaphore = asyncio.Semaphore(3)  # max 3 concurrent pages across all requests
    from core.harness.knowledge.wiki_engine import write_page
    async with _build_semaphore:
        chunks = [{"id": f"wiki-{page['title']}", "text": page["body"][:8000], "entities": []}]
        result = await engine.process_chunks(chunks, doc_id=f"wiki:{page['title']}")
        inst_count = len(result.instances) if hasattr(result, "instances") else 0

        if hasattr(result, "instances") and result.instances:
            for inst in result.instances[:3]:
                fm = inst.get("frontmatter", {})
                ititle = fm.get("title", "") or inst.get("entity_name", "")
                if ititle and ititle != page["title"]:
                    try:
                        await write_page(
                            title=ititle, body=fm.get("body", "") or str(fm.get("description", "") or ""),
                            category=fm.get("category", "entities"), collection_id=cid,
                        )
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)

        return {"title": page["title"], "instances": inst_count,
                "relations": len(result.relations) if hasattr(result, "relations") else 0}


@router.get("/engine/traces/{instance_title:path}", response_model=Dict[str, Any])
async def ontology_engine_trace(instance_title: str, doc_id: str = ""):
    """查询实例溯源。需提供 instance_title 和可选的 doc_id。"""
    import os as _os
    from pathlib import Path as _Path
    traces_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    safe = instance_title.replace("/", "_")[:120]
    trace_file = traces_dir / f"{safe}.json"
    if not trace_file.exists():
        raise HTTPException(status_code=404, detail=f"No trace found for '{instance_title}'")
    return _json.loads(trace_file.read_text(encoding="utf-8"))


@router.post("/engine/parse", response_model=Dict[str, Any])
async def ontology_engine_parse(req: dict):
    """解析文档 → 结构化Chunk → 本体引擎处理。
    
    支持: 文本字符串 + 格式参数
    
    请求体: {"text":"...", "format":"md|txt|html", "domain_id":"ai-knowledge"}
    """
    text = req.get("text", "") if isinstance(req, dict) else ""
    fmt = req.get("format", "txt") if isinstance(req, dict) else "txt"
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"

    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    # Step 1: Parse document
    from core.harness.ontology_engine.document_parser import DocumentParser
    parser = DocumentParser()
    parsed = parser.parse_text(text, format=fmt)

    # Step 2: Classify chunks
    from core.harness.ontology_engine.engine import load_engine
    engine = load_engine(domain_id)
    classifications = []
    if engine:
        from core.harness.ontology_engine.class_mapper import ClassMapper
        mapper = ClassMapper(engine._domain)
        for chunk in parsed.chunks:
            cls = mapper.classify_text(chunk.text, threshold=0.5)
            classifications.append({
                "chunk_id": chunk.id,
                "heading": " > ".join(chunk.heading_path) if chunk.heading_path else "",
                "text_preview": chunk.text[:120],
                "class": cls or "unknown",
            })

    return {
        "title": parsed.title,
        "format": parsed.format,
        "chunk_count": len(parsed.chunks),
        "classifications": classifications,
        "chunks": [c.to_dict() for c in parsed.chunks[:10]],  # First 10 only
        "warnings": parsed.parse_warnings,
    }


@router.post("/engine/parse-and-process", response_model=Dict[str, Any])
async def ontology_engine_parse_and_process(req: dict, collection: str = "default"):
    """解析文档 → 结构化Chunk → 本体引擎 → 自动写Wiki页面。
    
    完整链路: 上传文档 → 解析 → 类映射 → 属性提取 → 写入
    """
    from core.harness.ontology_engine.document_parser import DocumentParser
    from core.harness.ontology_engine.engine import load_engine

    text = req.get("text", "") if isinstance(req, dict) else ""
    fmt = req.get("format", "txt") if isinstance(req, dict) else "txt"
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    auto_write = bool(req.get("auto_write", False)) if isinstance(req, dict) else False

    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    # Parse
    parser = DocumentParser()
    parsed = parser.parse_text(text, format=fmt)

    # Engine process
    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    chunks = [c.to_dict() for c in parsed.chunks]
    result = await engine.process_chunks(chunks, doc_id=f"upload:{parsed.title}")

    # Write
    written = []
    if auto_write and result.instances:
        from core.harness.knowledge.wiki_engine import write_page
        for inst in result.instances:
            fm = inst.get("frontmatter", {})
            title = fm.get("title", "")
            if not title:
                continue
            try:
                await write_page(
                    title=title, body=str(fm.get("description", "") or ""),
                    category=fm.get("category", "entities"),
                    collection_id=collection,
                    tags=list(fm.get("tags", []) or []),
                    summary=str(fm.get("summary", "") or ""),
                )
                written.append(title)
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    return {
        **result.to_dict(),
        "parsed": {"title": parsed.title, "chunk_count": len(parsed.chunks), "warnings": parsed.parse_warnings},
        "written_pages": written,
    }


@router.post("/engine/simulate-state", response_model=Dict[str, Any])
async def simulate_state_transitions(req: dict):
    """模拟状态机：给定一批实例，返回状态转换链和受影响的实例。

    请求体: {
      "domain_id": "ai-knowledge",
      "instances": [
        {"class_name": "AI方法", "properties": {"name": "RAG", "maturity": "research"}, "chunk_id": "c0"},
        {"class_name": "AI系统", "properties": {"name": "SysA"}, "chunk_id": "c0"}
      ]
    }
    返回: { state_transitions, affected_instances, summary }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_instances = req.get("instances", []) if isinstance(req, dict) else []

    from core.harness.ontology_engine.engine import load_engine
    from core.harness.ontology_engine.state_machine import EvalContext

    engine = load_engine(domain_id)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    state_machine = getattr(engine, "_state_machine", None)
    if not state_machine:
        raise HTTPException(status_code=500, detail="State machine not initialized")

    # Normalize instances
    instances = []
    for i, ri in enumerate(raw_instances):
        instances.append({
            "class_name": str(ri.get("class_name", "")),
            "entity_text": str(ri.get("entity_text", "") or ri.get("properties", {}).get("name", f"inst-{i}")),
            "properties": dict(ri.get("properties", {}) or {}),
            "chunk_id": str(ri.get("chunk_id", f"sim-{i}")),
        })

    ctx = EvalContext(instances)
    state_transitions = []
    affected_instances = []

    for inst in instances:
        chain = state_machine.evaluate_chain(inst, ctx)
        if chain:
            for tres in chain:
                entry = tres.to_dict()
                entry["entity_text"] = inst["entity_text"]
                state_transitions.append(entry)
                # Collect affected: which other instances match side_effect targets
                for effect in tres.side_effects:
                    for action in effect.get("actions", []):
                        if action.get("type") == "mark_related_for_review":
                            rel = action.get("relation", "")
                            target_class = state_machine._relation_to_target_class(rel)
                            if target_class:
                                for other in instances:
                                    if other is not inst and other.get("class_name") == target_class:
                                        affected_instances.append({
                                            "from_instance": inst["entity_text"],
                                            "from_class": inst["class_name"],
                                            "to_instance": other["entity_text"],
                                            "to_class": other["class_name"],
                                            "reason": action.get("message", f"关联关系: {rel}"),
                                            "transition": f"{tres.from_state} → {tres.to_state}",
                                        })

    return {
        "state_transitions": state_transitions,
        "affected_instances": affected_instances,
        "summary": (
            f"{len(instances)} 实例 → {len(state_transitions)} 次状态转换"
            f"{', 影响 ' + str(len(affected_instances)) + ' 个关联实例' if affected_instances else ''}"
        ),
    }


@router.post("/engine/simulate-scenarios", response_model=Dict[str, Any])
async def simulate_scenarios(req: dict):
    """Multi-scenario simulation sandbox — compare different configurations side by side.

    请求体: {
      "domain_id": "ai-knowledge",
      "instances": [...],   # 基础实例
      "scenarios": [        # 多个场景对比
        {"label": "基线(无干预)", "instances": [...]},
        {"label": "方案A: 加强审查", "instances": [...]},
        {"label": "方案B: 自动放行", "instances": [...]}
      ]
    }
    返回: { domain_id, baseline: {...}, scenarios: [{label, ...}, ...], comparison: {...} }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_instances = req.get("instances", []) if isinstance(req, dict) else []
    raw_scenarios = req.get("scenarios", []) if isinstance(req, dict) else []

    from core.harness.ontology_engine.engine import load_engine
    from core.harness.ontology_engine.state_machine import EvalContext

    engine = load_engine(domain_id)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    state_machine = getattr(engine, "_state_machine", None)
    if not state_machine:
        raise HTTPException(status_code=500, detail="State machine not initialized")

    def _run_scenario(insts):
        normalized = []
        for i, ri in enumerate(insts):
            normalized.append({
                "class_name": str(ri.get("class_name", "")),
                "entity_text": str(ri.get("entity_text", "") or f"inst-{i}"),
                "properties": dict(ri.get("properties", {}) or {}),
                "chunk_id": str(ri.get("chunk_id", f"sim-{i}")),
            })
        ctx = EvalContext(normalized)
        trans = []
        affected = []
        for inst in normalized:
            chain = state_machine.evaluate_chain(inst, ctx)
            if chain:
                for tres in chain:
                    entry = tres.to_dict()
                    entry["entity_text"] = inst["entity_text"]
                    trans.append(entry)
        return {
            "instance_count": len(normalized),
            "state_transitions": trans,
            "transition_count": len(trans),
            "final_states": {inst["entity_text"]: inst.get("properties", {}).get("state", "unknown")
                             for inst in normalized if inst.get("properties", {}).get("state")},
        }

    # Run baseline
    baseline = _run_scenario(raw_instances) if raw_instances else {"instance_count": 0, "transition_count": 0}

    # Run each scenario
    scenario_results = []
    for sc in raw_scenarios:
        label = sc.get("label", f"Scenario {len(scenario_results)+1}")
        si = sc.get("instances", [])
        result = _run_scenario(si) if si else {"instance_count": 0, "transition_count": 0}
        result["label"] = label
        scenario_results.append(result)

    # Comparison
    comparison = {
        "baseline_transitions": baseline.get("transition_count", 0),
        "scenario_transitions": [r.get("transition_count", 0) for r in scenario_results],
        "scenario_labels": [r.get("label", "") for r in scenario_results],
    }

    return {
        "domain_id": domain_id,
        "baseline": baseline,
        "scenarios": scenario_results,
        "comparison": comparison,
    }


@router.get("/engine/reviews/{domain_id}", response_model=Dict[str, Any])
async def list_ontology_reviews(domain_id: str):
    """Get pending review queue for a domain ontology."""
    from pathlib import Path as _Path
    import os as _os, json as _json

    reviews_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_reviews"
    review_file = reviews_dir / f"{domain_id}.json"
    if not review_file.exists():
        return {"domain_id": domain_id, "reviews": [], "total": 0}
    try:
        reviews = _json.loads(review_file.read_text())
    except Exception:
        return {"domain_id": domain_id, "reviews": [], "total": 0}

    return {
        "domain_id": domain_id,
        "reviews": reviews,
        "total": len(reviews),
        "pending": sum(1 for r in reviews if r.get("status") == "pending"),
    }


@router.post("/engine/reviews/{domain_id}/resolve", response_model=Dict[str, Any])
async def resolve_ontology_review(domain_id: str, req: dict):
    """Mark a review as resolved."""
    from pathlib import Path as _Path
    import os as _os, json as _json

    review_id = req.get("review_id", "") if isinstance(req, dict) else ""
    if not review_id:
        raise HTTPException(status_code=400, detail="review_id required")

    reviews_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_reviews"
    review_file = reviews_dir / f"{domain_id}.json"
    if not review_file.exists():
        raise HTTPException(status_code=404, detail="No reviews for this domain")

    reviews = _json.loads(review_file.read_text())
    resolved = False
    for r in reviews:
        if r.get("id") == review_id:
            r["status"] = "resolved"
            resolved = True
            break
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")

    review_file.write_text(_json.dumps(reviews, ensure_ascii=False, indent=2))
    return {"review_id": review_id, "status": "resolved"}


@router.get("/engine/cross-domain-stats", response_model=Dict[str, Any])
async def get_cross_domain_stats():
    """Get aggregated stats across all domain graphs."""
    from core.harness.ontology_engine.engine import get_sharded_graph
    sharded = get_sharded_graph()
    # Load all domains
    for did in ["ai-knowledge", "default", "ship-design"]:
        sharded.get_shard(did)
    return {
        "total": sharded.total_stats(),
        "per_domain": sharded.stats_all(),
    }


@router.get("/engine/graph-stats/{domain_id}", response_model=Dict[str, Any])
async def get_graph_stats(domain_id: str):
    """Get graph statistics: nodes, edges, inferred edges."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    base = graph.stats()
    inferred = sum(1 for n in graph._nodes.values() for e in n.out_edges if getattr(e, "inferred", False))
    return {"domain_id": domain_id, "node_count": base["node_count"], "edge_count": base["edge_count"], "inferred_edges": inferred, "avg_degree": base["avg_degree"]}


@router.post("/engine/cross-source-resolve", response_model=Dict[str, Any])
async def cross_source_resolve(req: dict):
    """P1: Cross-source entity aggregation. Link entities from different data sources.

    请求体: {
      "domain_id": "ai-knowledge",
      "instances_a": [...],  // primary source
      "instances_b": [...],  // secondary source to link against
      "source_a": "wiki", "source_b": "erp"
    }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_a = req.get("instances_a", []) if isinstance(req, dict) else []
    raw_b = req.get("instances_b", []) if isinstance(req, dict) else []
    src_a = req.get("source_a", "") if isinstance(req, dict) else ""
    src_b = req.get("source_b", "") if isinstance(req, dict) else ""

    from core.harness.ontology_engine.entity_resolver import EntityResolver
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    domain = load_ontology_from_yaml(str(ont_path)) if ont_path.exists() else None
    resolver = EntityResolver(domain)

    def normalize(insts):
        return [{
            "class_name": str(x.get("class_name", "")),
            "entity_text": str(x.get("entity_text", "") or x.get("properties", {}).get("name", f"e{i}")),
            "properties": dict(x.get("properties", {}) or {}),
            "chunk_id": str(x.get("chunk_id", src_a if i < len(raw_a) else src_b)),
        } for i, x in enumerate(insts)]

    result = resolver.cross_source_resolve(
        normalize(raw_a), normalize(raw_b),
        source_a=src_a, source_b=src_b,
    )
    return result.to_dict()


@router.post("/engine/resolve", response_model=Dict[str, Any])
async def resolve_entities(req: dict):
    """Run entity resolver on a list of instances.

    请求体: {
      "domain_id": "ai-knowledge",
      "instances": [{"class_name":"AI方法","entity_text":"RAG","chunk_id":"c0"}, ...],
      "doc_type": "md"
    }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_instances = req.get("instances", []) if isinstance(req, dict) else []
    doc_type = req.get("doc_type", "") if isinstance(req, dict) else ""

    from core.harness.ontology_engine.entity_resolver import EntityResolver
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if not ont_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    domain = load_ontology_from_yaml(str(ont_path))
    resolver = EntityResolver(domain)
    normalized = []
    for i, ri in enumerate(raw_instances):
        normalized.append({
            "class_name": str(ri.get("class_name", "")),
            "entity_text": str(ri.get("entity_text", "") or ri.get("properties", {}).get("name", f"e{i}")),
            "chunk_id": str(ri.get("chunk_id", f"c{i}")),
            "properties": dict(ri.get("properties", {}) or {}),
        })
    result = resolver.resolve(normalized, doc_type=doc_type)
    return result.to_dict()


@router.get("/engine/state-history/{domain_id}", response_model=Dict[str, Any])
async def get_state_history(domain_id: str, entity: str = "", limit: int = 200):
    """Get state machine change history for a domain or specific entity."""
    from core.harness.ontology_engine.state_history import get_domain_history, get_entity_history

    if entity:
        history = get_entity_history(domain_id, entity)
        return {"domain_id": domain_id, "entity": entity, "history": history, "total": len(history)}
    else:
        history = get_domain_history(domain_id, limit)
        return {"domain_id": domain_id, "history": history, "total": len(history)}


@router.get("/engine/state-stats/{domain_id}", response_model=Dict[str, Any])
async def get_state_statistics(
    domain_id: str,
    entity: str = "",
    window: str = "24h",
    class_name: str = "",
):
    """Get time-series window statistics for state transitions.

    参数:
      entity:     filter by entity name (optional)
      window:     time window, e.g. "1h", "6h", "24h", "7d"
      class_name: filter by class (optional)

    返回:
      window_stats: sliding window metrics (velocity, distribution, chains)
      transition_rate: bucketed transition rate over time
      state_distribution: current state distribution across entities
    """
    from core.harness.ontology_engine.state_history import (
        get_entity_window_stats, get_domain_transition_rate, get_state_distribution
    )

    # Parse window
    w = window.lower()
    if w.endswith("h"):
        hours = float(w[:-1])
    elif w.endswith("d"):
        hours = float(w[:-1]) * 24
    else:
        hours = 24.0

    window_stats = get_entity_window_stats(
        domain_id, entity_name=entity, window_hours=hours, class_name=class_name,
    )
    rate = get_domain_transition_rate(domain_id, window_hours=hours, bucket_minutes=max(15, int(hours * 60 / 24)))
    distrib = get_state_distribution(domain_id, class_name=class_name)

    return {
        "domain_id": domain_id,
        "window": window,
        "entity": entity or "(all)",
        "window_stats": window_stats,
        "transition_rate": rate,
        "state_distribution": distrib,
    }


@router.post("/engine/traverse", response_model=Dict[str, Any])
async def graph_traverse(req: dict):
    """Multi-hop graph traversal from a start entity.

    请求体: {
      "domain_id": "ai-knowledge",
      "start_entity": "RAG",
      "max_hops": 2,
      "relation_types": ["implements", "applies"],
      "direction": "both"
    }
    返回: { paths, terminal_entities, stats }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    start_entity = req.get("start_entity", "") if isinstance(req, dict) else ""
    max_hops = int(req.get("max_hops", 2)) if isinstance(req, dict) else 2
    relation_types = req.get("relation_types") if isinstance(req, dict) else None
    direction = str(req.get("direction", "both")) if isinstance(req, dict) else "both"

    if not start_entity:
        raise HTTPException(status_code=400, detail="start_entity is required")

    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_traversal import traverse as _traverse

    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for domain '{domain_id}' is empty. Run engine first.")

    result = _traverse(
        start_entity=start_entity,
        graph=graph,
        max_hops=max_hops,
        relation_filter=relation_types,
        direction=direction,
    )

    return {
        "domain_id": domain_id,
        "start_entity": start_entity,
        **result.to_dict(),
    }


@router.post("/engine/feedback", response_model=Dict[str, Any])
async def submit_feedback(req: dict):
    """Submit user feedback on an answer.
    
    请求体: {"session_id":"...", "query":"...", "rating":4, "is_helpful":true, "domain_id":"default"}
    """
    from core.harness.ontology_engine.state_history import record_feedback
    sid = req.get("session_id", "") if isinstance(req, dict) else ""
    q = req.get("query", "") if isinstance(req, dict) else ""
    rating = int(req.get("rating", 0)) if isinstance(req, dict) else 0
    helpful = req.get("is_helpful") if isinstance(req, dict) else None
    domain = req.get("domain_id", "default") if isinstance(req, dict) else "default"
    record_feedback(session_id=sid, query_text=q, rating=rating, is_helpful=helpful, domain_id=domain)
    return {"status": "recorded"}


@router.get("/engine/feedback-stats/{domain_id}", response_model=Dict[str, Any])
async def get_feedback_statistics(domain_id: str):
    from core.harness.ontology_engine.state_history import get_feedback_stats
    return get_feedback_stats(domain_id)


@router.get("/engine/recommend/{domain_id}", response_model=Dict[str, Any])
async def get_knowledge_recommendations(
    domain_id: str,
    department: str = "",
    queries: str = "",
    limit: int = 5,
):
    """L5 active knowledge recommendation.

    Query: ?department=研发部&queries=RAG,知识检索&limit=5
    Returns ranked recommendations with reasons.
    """
    from core.harness.knowledge.wiki_engine import recommend_knowledge
    recent = [q.strip() for q in queries.split(",") if q.strip()] if queries else []
    result = recommend_knowledge(
        department=department, recent_queries=recent,
        domain_id=domain_id, limit=limit,
    )
    return {"domain_id": domain_id, "recommendations": result, "total": len(result)}


@router.post("/engine/parse-logic-form", response_model=Dict[str, Any])
async def parse_logic_form(req: dict):
    """NL2LF: Parse natural language to structured Logic Form."""
    from core.harness.knowledge.ontology_query_mapper import parse_to_logic_form
    query = req.get("query", "") if isinstance(req, dict) else ""
    if not query: raise HTTPException(status_code=400, detail="query required")
    return parse_to_logic_form(query)


@router.post("/engine/detect-gaps", response_model=Dict[str, Any])
async def detect_knowledge_gaps_endpoint(req: dict):
    """Detect knowledge gaps from query patterns.

    请求体: {
      "domain_id": "ai-knowledge",
      "queries": ["什么是RAG", "RAG怎么用", ...],
      "min_frequency": 2
    }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    queries = req.get("queries", []) if isinstance(req, dict) else []
    min_freq = int(req.get("min_frequency", 2)) if isinstance(req, dict) else 2

    from core.harness.ontology_engine.knowledge_gap_detector import detect_knowledge_gaps
    result = detect_knowledge_gaps(queries, domain_id=domain_id, min_frequency=min_freq)
    return {"domain_id": domain_id, **result}


@router.post("/engine/process-from-datasource", response_model=Dict[str, Any])
async def process_from_datasource(req: dict):
    """Palantir-style: process data from an external data source through the ontology engine.

    请求体: {"source_id": "erp_db", "domain_id": "ai-knowledge"}
    """
    from core.harness.ontology_engine.data_source import DataSourceRegistry
    from core.harness.ontology_engine.engine import load_engine

    source_id = req.get("source_id", "") if isinstance(req, dict) else ""
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"

    if not source_id:
        raise HTTPException(status_code=400, detail="source_id required")

    DataSourceRegistry.load_from_dir()
    engine = load_engine(domain_id)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    result = await engine.process_from_datasource(source_id)
    return {
        "source_id": source_id,
        "domain_id": domain_id,
        "instances": len(result.instances),
        "transitions": result.stats.get("state_transitions", 0),
        "warnings": result.warnings[:5],
        "errors": result.errors,
    }


@router.get("/datasources", response_model=Dict[str, Any])
async def list_datasources():
    from core.harness.ontology_engine.data_source import DataSourceRegistry
    DataSourceRegistry.load_from_dir()
    return {"datasources": DataSourceRegistry.list_sources()}


@router.post("/engine/synthesize", response_model=Dict[str, Any])
async def run_knowledge_synthesis(req: dict):
    """Synthesize graph knowledge into Wiki pages.

    请求体: {"domain_id": "ai-knowledge"}
    返回: { pages_written, chains, fact_cards, conclusions }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.knowledge_synthesis import KnowledgeSynthesizer

    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for '{domain_id}' is empty")

    synthesizer = KnowledgeSynthesizer(graph)
    result = synthesizer.synthesize(domain_id=domain_id, write_to_wiki=True)
    return {
        "domain_id": domain_id,
        **result.to_dict(),
    }


@router.post("/engine/snapshot/{domain_id}", response_model=Dict[str, Any])
async def create_graph_snapshot(domain_id: str, label: str = ""):
    """Create a versioned snapshot of the current graph state."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for '{domain_id}' is empty")
    result = graph.snapshot(label)
    return {"domain_id": domain_id, **result}


@router.get("/engine/snapshots/{domain_id}", response_model=Dict[str, Any])
async def list_graph_snapshots(domain_id: str):
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    return {"domain_id": domain_id, "snapshots": graph.list_snapshots()}


@router.post("/engine/snapshot/{domain_id}/restore", response_model=Dict[str, Any])
async def restore_graph_snapshot(domain_id: str, req: dict):
    snapshot_id = int(req.get("snapshot_id", 0)) if isinstance(req, dict) else 0
    if not snapshot_id:
        raise HTTPException(status_code=400, detail="snapshot_id required")
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    result = graph.restore_snapshot(snapshot_id)
    return {"domain_id": domain_id, **result}


@router.get("/sdk/{domain_id}", response_model=Dict[str, Any])
async def generate_ontology_sdk(domain_id: str, language: str = "python"):
    """Generate a client SDK from the domain ontology YAML.

    Produces dataclass definitions with fields, enums, state machines,
    and API wrappers for all CRUD operations on the domain.

    Query: ?language=python|typescript
    """
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if not ont_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    domain = load_ontology_from_yaml(str(ont_path))

    if language == "python":
        lines = [f'"""Auto-generated SDK for {domain.name} domain — v{domain.version}."""', '',
                 'from dataclasses import dataclass, field', 'from typing import List, Optional', '',
                 f'# {domain.description}', f'# Generated from: {domain_id}.yaml', '']
        for cls in domain.classes:
            lines.append('@dataclass')
            lines.append(f'class {cls.label}:')
            lines.append(f'    """{cls.description}"""')
            for rf in cls.required_fields:
                lines.append(f'    {rf}: str  # required')
            for of in cls.optional_fields:
                lines.append(f'    {of}: Optional[str] = None')
            lines.append(f'    tags: List[str] = field(default_factory=list)')
            if getattr(cls, 'states', None):
                states = getattr(cls, 'states', {})
                def_state = states.get('default', 'unknown')
                lines.append(f'    state: str = "{def_state}"')
                enums = states.get('enum', [])
                if enums:
                    evals = [s['name'] for s in enums]
                    lines.append(f'    # Valid states: {", ".join(evals)}')
            lines.append('')

        lines.append('# ── API Client ──')
        lines.append(f'BASE = "http://localhost:8002/api/core/wiki/ontology"')
        lines.append('')
        lines.append('async def search_pages(query: str, limit: int = 10):')
        lines.append('    import aiohttp')
        lines.append(f'    async with aiohttp.ClientSession() as s:')
        lines.append(f'        async with s.get(f"{{BASE}}/../pages?q={{query}}&limit={{limit}}") as r:')
        lines.append(f'            return await r.json()')

        return {"domain_id": domain_id, "language": language, "code": "\n".join(lines)}

    elif language == "typescript":
        ts = [f'// Auto-generated SDK for {domain.name} domain — v{domain.version}',
              f'// {domain.description}', '']
        for cls in domain.classes:
            ts.append(f'export interface {cls.label} {{')
            for rf in cls.required_fields:
                ts.append(f'  {rf}: string;  // required')
            for of in cls.optional_fields:
                ts.append(f'  {of}?: string;')
            ts.append(f'  tags: string[];')
            if getattr(cls, 'states', None):
                ts.append(f'  state: string;')
            ts.append('}')
            ts.append('')
        return {"domain_id": domain_id, "language": language, "code": "\n".join(ts)}

    raise HTTPException(status_code=400, detail=f"Unsupported language: {language}. Use python or typescript")


@router.post("/engine/infer", response_model=Dict[str, Any])
async def run_graph_inference(req: dict):
    """Run inference rules on the domain graph to derive new edges.

    请求体: {"domain_id": "ai-knowledge"}
    返回: { inferred_edges, rule_hits, stats }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"

    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_inference import GraphInference
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if not ont_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    domain = load_ontology_from_yaml(str(ont_path))
    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for '{domain_id}' is empty")

    inferencer = GraphInference(domain, graph)
    result = inferencer.infer()
    applied = inferencer.apply_to_graph(result)
    if applied:
        graph.save()

    return {
        "domain_id": domain_id,
        "applied": applied,
        **result.to_dict(),
    }



class OntologyDomainCreate(BaseModel):
    id: str = Field(min_length=1, max_length=50, description="域标识 (如 ai-knowledge)")
    name: str = Field(min_length=1, max_length=100, description="显示名 (如 AI知识)")
    namespace: str = ""
    description: str = ""
    version: str = "1.0.0"

class OntologyClassCreate(BaseModel):
    name: str
    label: str
    description: str = ""
    required_fields: list = []
    optional_fields: list = []
    categories: list = []
    parent: str = ""

class OntologyPropertyCreate(BaseModel):
    name: str
    label: str
    domain: list = []
    range: list = []
    transitive: bool = False
    symmetric: bool = False


def _remove_from_registry(domain_id: str) -> None:
    """Remove a domain from registry.json."""
    from pathlib import Path as _Path
    import os as _os, json
    registry_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / "registry.json"
    if not registry_path.exists():
        return
    with open(registry_path, "r", encoding="utf-8") as f:
        reg = json.load(f)
    reg.get("domains", {}).pop(domain_id, None)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def _write_domain_yaml(domain_id: str, data: dict) -> None:
    """Save domain ontology back to YAML file."""
    import yaml as _yaml
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    d.mkdir(parents=True, exist_ok=True)
    file_path = d / f"{domain_id}.yaml"
    # Preserve order with safe_dump
    content = _yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    file_path.write_text(f"# {data.get('name', domain_id)} 领域本体模型\n{content}", encoding="utf-8")


# ── Placeholder endpoints for frontend-contracted features (v2.4) ──

@router.post("/engine/parse", response_model=Dict[str, Any])
async def ontology_engine_parse(body: Dict[str, Any]):
    """Parse raw text/document into structured ontology entities (planned)."""
    raise HTTPException(status_code=501, detail="Not implemented — parse pipeline in development")


@router.post("/engine/parse-and-process", response_model=Dict[str, Any])
async def ontology_engine_parse_and_process(body: Dict[str, Any]):
    """Parse and immediately process into GraphIndex (planned)."""
    raise HTTPException(status_code=501, detail="Not implemented — parse-and-process pipeline in development")


@router.post("/engine/feedback", response_model=Dict[str, Any])
async def ontology_engine_feedback(body: Dict[str, Any]):
    """Receive ontology feedback from UI interactions (planned)."""
    raise HTTPException(status_code=501, detail="Not implemented — feedback collection in development")



