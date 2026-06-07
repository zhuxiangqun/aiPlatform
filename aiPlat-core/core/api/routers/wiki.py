"""
Wiki API — persistent LLM-curated knowledge base endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

router = APIRouter(prefix="/wiki", tags=["wiki"])

# ── Request Models ──────────────────────────────────────────────

class ConvertKbRequest(BaseModel):
    tenant_id: str = "default"
    collection_id: str = "default"
    limit: int = 50
    doc_ids: Optional[List[str]] = None


class WikiPageWrite(BaseModel):
    title: str
    body: str
    category: str = "entities"
    tags: List[str] = []
    related: List[str] = []
    summary: str = ""


class WikiIngest(BaseModel):
    source_text: str
    source_title: str = ""
    source_url: str = ""


class AtomizeRequest(BaseModel):
    doc_text: str
    doc_id: str = ""
    max_atoms: int = 20
    model_name: str = ""


class CollectionCreate(BaseModel):
    collection_id: str


@router.get("/pages")
async def list_pages(
    category: str = "",
    tag: str = "",
    query: str = "",
    source: str = "",
    limit: int = 100,
    offset: int = 0,
    collection: str = "default",
):
    from core.harness.knowledge.wiki_engine import search_pages, list_all_pages
    if query or tag:
        tags = [tag] if tag else None
        pages = search_pages(query=query, tags=tags, category=category, limit=limit, collection_id=collection)
    else:
        pages = list_all_pages(collection_id=collection)
        if category:
            pages = [p for p in pages if p["category"] == category]
        pages = pages[offset:offset + limit]
    # Filter by source_articles prefix
    if source:
        pages = [p for p in pages if any(
            s.startswith(source + ":") for s in (p.get("source_articles") or [])
        )]
    return {"items": pages, "total": len(pages)}


@router.get("/pages/{title}")
async def read_page(title: str, category: str = "entities", collection: str = "default"):
    from core.harness.knowledge.wiki_engine import read_page
    page = read_page(title, category=category, collection_id=collection)
    if not page:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")

    # ── Inference injection: add inferred relations ──
    import os as _os
    if _os.getenv("AIPLAT_WIKI_INFERENCE_ENABLED", "false").lower() in ("1", "true"):
        try:
            from core.harness.knowledge.knowledge_abox_builder import build_abox
            from core.harness.knowledge.knowledge_validator import TripleStore, _short, run_full_inference
            onto = build_abox(collection_id=collection)
            store = TripleStore(onto.triples)
            inference = run_full_inference(store)

            page_uri = f"http://aiplat.local/knowledge#{title}"
            inferred = []
            for kind in ("transitive", "source_chain"):
                for inf in inference.get(kind, []):
                    if inf.get("subject") == page_uri or inf.get("object") == page_uri:
                        pred = inf["predicate"].replace("http://aiplat.local/knowledge#", "")
                        target = _short(inf["object"]) if inf["subject"] == page_uri else _short(inf["subject"])
                        inferred.append({
                            "type": pred,
                            "target": target,
                            "direction": "out" if inf["subject"] == page_uri else "in",
                            "provenance": kind,
                        })
            if inferred:
                page["inferred_relations"] = inferred
        except Exception:
            pass

    return page


@router.delete("/pages/{title}")
async def delete_page(title: str, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import delete_page as _del
    ok = _del(title, collection_id=collection)
    if not ok:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")
    return {"title": title, "status": "deleted"}


@router.delete("/pages-all")
async def delete_all_pages(collection: str = "default"):
    from core.harness.knowledge.wiki_engine import delete_all_pages
    result = delete_all_pages(collection_id=collection)
    return {"deleted": result["deleted"], "message": f"已清空 {result['deleted']} 个 Wiki 页面"}


@router.get("/unprocessed-docs")
async def get_unprocessed_docs(tenant_id: str = "default", collection: str = "default"):
    u"""Return KB documents that don't have corresponding wiki pages.
    
    Cross-references wiki page source_articles (kb:doc_id) with
    KB documents table. No platform auth required.
    """
    import os, json as _json, sqlite3 as _sq
    from core.harness.knowledge.wiki_engine import search_pages
    
    kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    kb_db = os.path.join(kb_dir, tenant_id, "kb.sqlite3")
    if not os.path.exists(kb_db):
        return {"items": [], "total": 0}
    
    # Get all wiki-sourced KB doc_ids
    wiki_pages = search_pages(limit=1000, collection_id=collection)
    wiki_doc_ids = set()
    for p in wiki_pages:
        for s in (p.get("source_articles") or []):
            if s.startswith("kb:"):
                wiki_doc_ids.add(s.replace("kb:", ""))
    
    # Find KB docs not in wiki
    conn = _sq.connect(kb_db)
    conn.row_factory = _sq.Row
    docs = conn.execute(
        "SELECT doc_id, source_uri, kind, status FROM documents WHERE tenant_id=? AND status='ready'",
        (tenant_id,)
    ).fetchall()
    
    unprocessed = []
    for d in docs:
        if d["doc_id"] not in wiki_doc_ids:
            unprocessed.append({
                "doc_id": d["doc_id"],
                "source_uri": d["source_uri"],
                "kind": d["kind"],
                "status": d["status"],
            })
    conn.close()
    return {"items": unprocessed, "total": len(unprocessed)}


@router.get("/skill-deps")
async def get_skill_deps():
    u"""Return Agent→Skill→Syscall dependency graph."""
    from core.harness.knowledge.skill_deps import build_skill_deps
    return build_skill_deps()


@router.get("/skill-impact/{skill_id}")
async def get_skill_impact(skill_id: str):
    u"""Return agents and skills affected by a given skill."""
    from core.harness.knowledge.skill_deps import skill_impact
    result = skill_impact(skill_id)
    if not result.get("exists"):
        raise HTTPException(status_code=404, detail="skill not found")
    return result


@router.get("/proposals")
async def get_proposals(status: str = "", collection: str = "default"):
    u"""List pending wiki knowledge proposals (merge/update/supplement/contradict)."""
    from core.harness.knowledge.wiki_engine import load_proposals
    proposals = load_proposals(collection_id=collection)
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return {"items": proposals, "total": len(proposals)}


@router.put("/proposals/{proposal_id}")
async def handle_proposal(proposal_id: str, body: Dict[str, Any], collection: str = "default"):
    u"""Approve/reject a proposal. Body: {status: 'approved'|'rejected'}."""
    from core.harness.knowledge.wiki_engine import update_proposal_status, apply_proposal
    status = body.get("status", "")
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")
    ok = update_proposal_status(proposal_id, status, collection_id=collection)
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    result = {"proposal_id": proposal_id, "status": status}
    # If approved, execute the proposal action
    if status == "approved":
        result["execution"] = apply_proposal(proposal_id, collection_id=collection)
    return result


@router.post("/pages")
async def create_wiki_page(body: WikiPageWrite, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import write_page, auto_link_page, search_pages, update_page
    try:
        path = write_page(body.title, body.body, category=body.category,
                          tags=body.tags, related=body.related, summary=body.summary,
                          collection_id=collection)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Auto-link via embedding similarity (through infra adapter)
    auto_links = []
    try:
        all_titles = [p["title"] for p in search_pages(limit=500, collection_id=collection)]
        auto_links = auto_link_page(body.title, body.body, all_titles)
        if auto_links:
            update_page(body.title, related=list(set(body.related or [] + auto_links)), collection_id=collection)
    except Exception:
        pass
    return {"title": body.title, "path": path, "status": "created", "auto_links": auto_links}


@router.get("/traverse/{title}")
async def traverse_links(title: str, depth: int = 2, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import traverse_links
    pages = traverse_links(title, depth=depth, collection_id=collection)
    return {"root": title, "depth": depth, "pages": len(pages), "items": pages}


@router.get("/lint")
async def lint_wiki(collection: str = "default"):
    from core.harness.knowledge.wiki_engine import wiki_health_report
    return wiki_health_report()


@router.get("/graph")
async def wiki_graph(
    category: str = "",
    keyword: str = "",
    source: str = "",
    max_nodes: int = 300,
 collection: str = "default"):
    from core.harness.knowledge.wiki_engine import build_graph
    return build_graph(category=category, keyword=keyword, source=source, max_nodes=max_nodes, collection_id=collection)


@router.post("/ingest")
async def ingest_text(body: WikiIngest):
    """Submit text for wiki processing. The wiki_curator agent handles this asynchronously."""
    import uuid, time
    from core.harness.knowledge.wiki_engine import write_page, _wiki_root
    # Store raw source for later processing
    source_dir = _wiki_root() / "_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    sid = f"src_{uuid.uuid4().hex[:8]}"
    import json as _json
    (source_dir / f"{sid}.json").write_text(_json.dumps({
        "id": sid, "title": body.source_title, "text": body.source_text[:50000],
        "url": body.source_url, "ingested_at": time.time(),
    }, ensure_ascii=False))
    return {"source_id": sid, "status": "ingested",
            "message": "Text stored. Execute wiki_curator agent to process and update wiki pages."}


@router.post("/atomize-document")
async def atomize_document(body: AtomizeRequest, collection: str = "default"):
    """Ontology-driven atom extraction: raw document → KnowledgeAtoms with evidence.

    Uses T-Box schema to guide LLM extraction of claims with precise source positions.
    Each atom includes: evidence_start, evidence_end, evidence_text, confidence.
    Automatically detects contradictions and creates ContradictionPages.
    """
    import asyncio
    from core.harness.knowledge.wiki_engine import atomize_document as _atomize

    doc_id = body.doc_id or f"doc_{abs(hash(body.doc_text[:100])) % 10**12:012d}"
    try:
        result = await _atomize(
            body.doc_text, doc_id,
            collection_id=collection,
            max_atoms=body.max_atoms,
            model_name=body.model_name,
        )
        return {
            "doc_id": doc_id,
            "atoms_extracted": result["atoms_extracted"],
            "atoms_written": result["atoms_written"],
            "contradictions_found": result["contradictions_found"],
            "contradiction_pages_created": result["contradiction_pages_created"],
            "error": result.get("error"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Atomization failed: {e}")


@router.post("/convert-from-kb")
async def convert_from_kb(req: ConvertKbRequest = Body(default=None), collection: str = "default"):
    u"""Convert existing KB documents into Wiki pages.
    
    If doc_ids is provided, only those specific documents are converted.
    Otherwise all documents matching tenant/collection are processed.
    """
    tenant_id = req.tenant_id if req else "default"
    collection_id = req.collection_id if req else "default"
    limit = req.limit if req else 50
    doc_ids = req.doc_ids if req else None
    import os, re, time as _time, logging
    logger = logging.getLogger(__name__)
    from core.harness.knowledge.wiki_engine import write_page, _wiki_root

    docs_converted = 0
    entities_created = 0
    uploads_converted = 0
    skipped = 0
    writeback_errors = 0
    errors = []

    try:
        # Read KB documents from platform KB storage
        kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
        kb_db = os.path.join(kb_dir, tenant_id, "kb.sqlite3")
        if not os.path.exists(kb_db):
            return {"docs_converted": 0, "entities_created": 0, "uploads_converted": 0, "skipped": 0, "writeback_errors": 0, "errors": ["KB database not found. Ensure documents are ingested into the knowledge base first."]}

        import sqlite3, json as _json
        conn = sqlite3.connect(kb_db)
        conn.row_factory = sqlite3.Row
        try:
            # Read documents from 'documents' table
            if doc_ids and len(doc_ids) > 0:
                placeholders = ','.join('?' * len(doc_ids))
                sql = f"SELECT doc_id, source_uri, kind, status, meta_json, created_at FROM documents WHERE tenant_id=? AND collection_id=? AND doc_id IN ({placeholders}) ORDER BY created_at DESC LIMIT ?"
                docs = conn.execute(sql, (tenant_id, collection_id, *doc_ids, limit)).fetchall()
            else:
                docs = conn.execute(
                    "SELECT doc_id, source_uri, kind, status, meta_json, created_at FROM documents WHERE tenant_id=? AND collection_id=? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, collection_id, limit)
                ).fetchall()

            if not docs:
                return {"docs_converted": 0, "entities_created": 0, "uploads_converted": 0, "skipped": 0, "writeback_errors": 0, "errors": ["No documents found in KB. Ingest documents first via Knowledge Base page."]}

            topic_keywords = {}  # Track shared keywords across documents for cross-linking

            for doc in docs:
                doc_id = doc["doc_id"]
                source_uri = str(doc["source_uri"] if "source_uri" in doc.keys() else doc_id)
                # Extract title from filename or meta
                title = os.path.basename(source_uri).rsplit(".", 1)[0][:100] or doc_id[:60]
                # Try to get title from meta_json
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    if meta.get("title"):
                        title = str(meta["title"])[:120]
                except: pass
                # Try to parse a human-readable title from the URI
                from core.harness.knowledge.wiki_engine import parse_title_from_uri
                readable = parse_title_from_uri(source_uri)
                if readable and len(readable) >= 3:
                    title = readable

                # Skip if already converted
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    wiki_pages = meta.get("wiki_pages", [])
                    if wiki_pages:
                        skipped += 1
                        continue
                except: pass

                # Read document elements (full text)
                elements = conn.execute(
                    "SELECT text FROM kb_elements WHERE tenant_id=? AND doc_id=? ORDER BY page_idx, element_id",
                    (tenant_id, doc_id)
                ).fetchall()

                if not elements:
                    skipped += 1
                    continue

                # Build body from elements
                body_parts = []
                for el in elements:
                    text = str(el["text"] or "").strip()
                    if text:
                        body_parts.append(text)
                body = "\n\n".join(body_parts)[:50000]

                # Extract keywords for auto-tagging
                keywords = re.findall(r'[\u4e00-\u9fff]{2,8}|[A-Z][a-zA-Z]{2,}', body[:5000])
                tags = list(set(kw.lower() for kw in keywords[:8]))
                summary = body[:300].replace("\n", " ")

                # Track keywords for cross-linking
                for kw in tags[:5]:
                    if kw not in topic_keywords:
                        topic_keywords[kw] = []
                    topic_keywords[kw].append(title)

                # Create wiki page
                safe_title = re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
                write_page(safe_title, body, category="entities", tags=tags, summary=summary,
                          source_articles=[f"kb:{doc_id}"], collection_id=collection)
                docs_converted += 1

                # LLM curation: enhance with proper summary, entity extraction, auto-linking
                try:
                    from core.harness.knowledge.wiki_engine import llm_curate_page, list_all_pages as _lap
                    existing = _lap()
                    existing_titles = [p["title"] for p in existing] if existing else []
                    curated = await llm_curate_page(safe_title, body, existing_titles=existing_titles, source_doc_id=doc_id)
                    # Re-write with LLM-enhanced metadata
                    old_title = safe_title
                    write_page(curated["title"], body,
                        category=curated.get("category", "entities"),
                        tags=curated.get("tags", tags),
                        related=curated.get("related", []),
                        summary=curated.get("summary", summary),
                        source_articles=[f"kb:{doc_id}"], collection_id=collection)
                    # If LLM changed the title, delete the mechanically-created page
                    if curated["title"] != old_title:
                        from core.harness.knowledge.wiki_engine import delete_page as _delp
                        try: _delp(old_title)
                        except: pass
                    # Always delete the mechanical page if it still exists
                    from core.harness.knowledge.wiki_engine import delete_page as _delp2
                    try: _delp2(old_title)
                    except: pass
                    # Create knowledge atom pages with evidence tracking
                    for atom in curated.get("knowledge_atoms", [])[:8]:
                        if not atom.get("title") or not atom.get("body"):
                            continue
                        atom_title = re.sub(r"[<>:\"/\\|?*]", "_", str(atom["title"])[:80])
                        if atom_title and atom_title != curated["title"]:
                            from core.harness.knowledge.wiki_engine import write_atom
                            write_atom({
                                "title": atom_title,
                                "body": str(atom.get("body", ""))[:20000],
                                "source_doc_id": f"kb:{doc_id}",
                                "evidence_text": atom.get("evidence_text", ""),
                                "confidence": float(atom.get("confidence", 0.5)),
                                "tags": list(atom.get("tags", []))[:5],
                                "contradicts_atom_index": atom.get("contradicts_atom_index"),
                                "supports_atom_index": atom.get("supports_atom_index"),
                            }, collection_id=collection)
                            entities_created += 1
                    # After creating knowledge atoms, update main page's related
                    # to include them (prevent orphan pages)
                    if entities_created > 0 and curated.get("title"):
                        main_page = read_page(curated["title"], collection_id=collection)
                        if main_page:
                            atom_titles = []
                            for atom in curated.get("knowledge_atoms", [])[:8]:
                                a_title = re.sub(r"[<>:\"/\\|?*]", "_", str(atom.get("title", ""))[:80])
                                if a_title and a_title != curated["title"]:
                                    atom_titles.append(a_title)
                            if atom_titles:
                                existing_related = set(main_page.get("related", []) or [])
                                existing_related.update(atom_titles)
                                write_page(curated["title"], main_page.get("body", "", collection_id=collection),
                                    category=main_page.get("category", "entities"),
                                    tags=main_page.get("tags", []),
                                    related=list(existing_related)[:10],
                                    summary=main_page.get("summary", ""))
                    # Mark contradictions
                    for con in curated.get("contradictions", [])[:3]:
                        from core.harness.knowledge.wiki_engine import read_page as _rpx
                        old_page = _rpx(con.get("b", ""))
                        if old_page:
                            old_contradictions = set(old_page.get("contradictions", []))
                            old_contradictions.add(safe_title)
                            write_page(con.get("b", "", collection_id=collection), old_page.get("body", ""),
                                category=old_page.get("category", "entities"),
                                tags=old_page.get("tags", []), related=old_page.get("related", []),
                                contradictions=list(old_contradictions)[:10])
                except Exception:
                    pass  # LLM curation best-effort

                # Write back to KB document: record linked wiki page
                final_title = curated["title"] if curated.get("title") and curated["title"] != old_title else safe_title
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    wiki_pages = meta.get("wiki_pages", [])
                    # Remove old mechanical title if it differs from final
                    if final_title != safe_title and safe_title in wiki_pages:
                        wiki_pages.remove(safe_title)
                    if final_title not in wiki_pages:
                        wiki_pages.append(final_title)
                        meta["wiki_pages"] = wiki_pages
                        meta_json_str = _json.dumps(meta, ensure_ascii=False)
                        conn.execute("UPDATE documents SET meta_json=?, wiki_status='wikified' WHERE doc_id=? AND tenant_id=?",
                                    (meta_json_str, doc_id, tenant_id))
                        conn.commit()
                except Exception as e:
                    writeback_errors += 1
                    logger.warning(f"convert-from-kb: failed to write wiki_pages for doc {doc_id}: {e}")

            # Cross-link pages that share keywords (validate against actual existing pages)
            valid_titles = set()
            try:
                from core.harness.knowledge.wiki_engine import search_pages
                valid_titles = set(p["title"] for p in (search_pages(limit=1000, collection_id=collection) or []))
            except Exception:
                pass
            for kw, titles in topic_keywords.items():
                if len(titles) >= 2:
                    # Filter out titles that don't correspond to actual wiki pages
                    real_titles = [t for t in titles if t in valid_titles]
                    if len(real_titles) < 2:
                        continue
                    for t in real_titles:
                        related = [t2 for t2 in real_titles if t2 != t]
                        from core.harness.knowledge.wiki_engine import read_page
                        page = read_page(t, category="entities", collection_id=collection)
                        if page:
                            existing = set(page.get("related", []))
                            existing.update(related[:5])
                            write_page(t, page.get("body", "", collection_id=collection), category="entities",
                                       tags=page.get("tags", []), related=list(existing)[:10])

            conn.close()
        finally:
            conn.close()

    except Exception as e:
        errors.append(str(e)[:500])

    # Also scan uploads/ directory for files not yet in wiki (skip when specific doc_ids given)
    if not doc_ids:
        try:
            uploads_dir = os.path.join(kb_dir, tenant_id, "uploads")
            if os.path.exists(uploads_dir):
                from core.harness.knowledge.wiki_engine import search_pages
                existing_wiki = set(p["title"] for p in search_pages(limit=1000, collection_id=collection))

                for fname in os.listdir(uploads_dir):
                    fpath = os.path.join(uploads_dir, fname)
                    if not os.path.isfile(fpath): continue
                    if fname.startswith("."): continue
                    if fname.startswith("preview_"): continue  # skip intermediate preview files
                    # Skip if this upload file is already a KB document with wiki pages
                    try:
                        kb_docs = conn.execute(
                            "SELECT meta_json FROM documents WHERE source_uri LIKE ? AND tenant_id=?",
                            (f"%{fname}%", tenant_id)
                        ).fetchall()
                        already_converted = False
                        for kd in kb_docs:
                            km = _json.loads(kd["meta_json"] or "{}")
                            if km.get("wiki_pages"):
                                already_converted = True
                                break
                        if already_converted: continue
                    except: pass

                    title = os.path.splitext(fname)[0][:100]
                    title = re.sub(r"[<>:\"/\\|?*]", "_", title)
                    if title in existing_wiki: continue

                    # Try to read the file
                    try:
                        with open(fpath, "rb") as fh:
                            raw = fh.read(10000)
                        try:
                            body = raw.decode("utf-8")
                        except:
                            body = raw.decode("utf-8", errors="replace")
                    except:
                        continue
                    if not body or len(body) < 50:
                        continue

                    tags = list(set(kw.lower() for kw in re.findall(r'[\u4e00-\u9fff]{2,8}|[A-Z][a-zA-Z]{2,}', body[:5000])))[:8]
                    write_page(title, body[:50000], category="entities", tags=tags,
                              summary=body[:300].replace("\n", " "),
                              source_articles=[f"upload:{fname}"], collection_id=collection)
                    uploads_converted += 1
                    # Mark as processed
                    try:
                        import sqlite3 as _sq
                        c2 = _sq.connect(kb_db)
                        existing = c2.execute("SELECT 1 FROM documents WHERE doc_id LIKE ?", (f"%{fname[:20]}%",)).fetchone()
                        c2.close()
                    except: pass
                    if uploads_converted >= limit * 2:
                        break
        except Exception as e:
            if not errors: errors.append(f"upload scan: {str(e)[:200]}")

    total = docs_converted + entities_created + uploads_converted
    return {
        "docs_converted": docs_converted,
        "entities_created": entities_created,
        "uploads_converted": uploads_converted,
        "skipped": skipped,
        "writeback_errors": writeback_errors,
        "errors": errors,
        "message": f"转换 {docs_converted} 个文档 + {entities_created} 个实体 + {uploads_converted} 个孤立文件。{skipped} 个已跳过。{f'({writeback_errors} 写回失败)' if writeback_errors else ''}",
    }


@router.post("/curate")
async def curate_wiki(collection: str = "default"):
    u"""LLM 深度策展：遍历所有 Wiki 页面，用 LLM 重写标题/分类/标签/摘要/关联。

    返回: {processed, links_added, titles_updated, errors[]}
    如果 LLM 不可用，降级到嵌入自动关联。
    """
    from core.harness.knowledge.wiki_engine import search_pages, llm_curate_page, update_page, auto_link_page
    pages = search_pages(limit=500, collection_id=collection)
    report = {"processed": 0, "links_added": 0, "titles_updated": 0, "errors": []}
    all_titles = [p["title"] for p in pages]

    # Track saved proposals to detect conflicts (same pair, different action)
    saved_pairs: Dict[frozenset, str] = {}

    for p in pages:
        try:
            existing_titles = [t for t in all_titles if t != p["title"]]
            result = await llm_curate_page(p["title"], p.get("body", ""),
                                           existing_titles=existing_titles)
            if result.get("error") or result.get("fallback"):
                # LLM failed → try embedding auto-link as fallback
                report["errors"].append({
                    "page": p["title"],
                    "error": result.get("error", "LLM unavailable"),
                })
                auto_rel = auto_link_page(p["title"], p.get("body", ""), existing_titles)
                if auto_rel:
                    update_page(p["title"], related=auto_rel)
                    report["links_added"] += len(auto_rel)
                    report["processed"] += 1
                continue

            update_page(p["title"],
                        new_title=result.get("title"),
                        category=result.get("category"),
                        tags=result.get("tags"),
                        summary=result.get("summary"),
                        related=result.get("related", []))  # replace, not merge (LLM curates against current titles)
            report["processed"] += 1
            report["links_added"] += len(result.get("related", []))
            if result.get("title") != p["title"]:
                report["titles_updated"] += 1
            # Generate proposals for merge / update / supplement
            import time as _t
            for mc in result.get("merge_candidates", [])[:3]:
                if mc.get("target") and mc["target"] in existing_titles:
                    from core.harness.knowledge.wiki_engine import save_proposal
                    pair = frozenset([p["title"], mc["target"]])
                    if pair in saved_pairs and saved_pairs[pair] != "merge":
                        report["errors"].append({
                            "page": p["title"],
                            "error": f"conflicting proposal: merge→{mc['target']} vs existing {saved_pairs[pair]}",
                        })
                        continue
                    save_proposal({
                        "action": "merge",
                        "from_title": p["title"],
                        "to_title": mc["target"],
                        "reason": str(mc.get("reason", "content overlap")),
                        "source_doc": "",
                        "status": "pending",
                        "created_at": str(int(_t.time())),
                    }, collection_id=collection)
                    saved_pairs[pair] = "merge"
            for con in result.get("contradictions", [])[:3]:
                b_title = con.get("b", "") if isinstance(con, dict) else con
                if b_title and b_title in existing_titles:
                    from core.harness.knowledge.wiki_engine import save_proposal
                    pair = frozenset([p["title"], b_title])
                    if pair in saved_pairs and saved_pairs[pair] != "contradict":
                        report["errors"].append({
                            "page": p["title"],
                            "error": f"conflicting proposal: contradict↔{b_title} vs existing {saved_pairs[pair]}",
                        })
                        continue
                    save_proposal({
                        "action": "contradict",
                        "from_title": p["title"],
                        "to_title": b_title,
                        "reason": str(con.get("detail", "conflicting claims") if isinstance(con, dict) else "conflicting claims"),
                        "source_doc": "",
                        "status": "pending",
                        "created_at": str(int(_t.time())),
                    }, collection_id=collection)
                    saved_pairs[pair] = "contradict"
        except Exception as e:
            report["errors"].append({"page": p["title"], "error": str(e)[:300]})

    return report


@router.post("/wiki/index-md")
async def regenerate_wiki_index(collection: str = "default"):
    """Generate a human-readable wiki index page (index.md) from index.json."""
    try:
        from core.harness.knowledge.wiki_engine import generate_index_md
        content = generate_index_md(collection_id=collection)
        lines = content.count("\n") + 1 if content else 0
        return {"status": "ok", "lines": lines, "content": content[:500]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index generation failed: {e}")


@router.get("/wiki/health-trend")
async def get_wiki_health_trend():
    """Get wiki health score trend over time."""
    try:
        from core.harness.knowledge.wiki_health_rules import get_health_trend
        return get_health_trend()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get health trend: {e}")


@router.get("/wiki/golden-queries/seed")
async def seed_golden_queries():
    """Create a default golden_queries.yaml template."""
    try:
        from core.harness.knowledge.wiki_structured_query import seed_golden_queries
        return {"status": seed_golden_queries()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {e}")


@router.post("/wiki/golden-queries/run")
async def run_golden_tests():
    """Run regression tests against golden queries."""
    try:
        from core.harness.knowledge.wiki_structured_query import run_golden_tests
        return run_golden_tests()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Golden test failed: {e}")


@router.get("/wiki/query-structured")
async def wiki_structured_query(q: str = ""):
    """Deterministic structured query — same question, same answer."""
    if not q:
        return {"error": "Missing query parameter ?q=", 
                "examples": ["?q=什么是RAG", "?q=RAG与Wiki有什么区别", "?q=wiki健康报告"]}
    try:
        from core.harness.knowledge.wiki_structured_query import structured_query
        return structured_query(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Structured query failed: {e}")


@router.get("/wiki/golden-queries/seed")
async def seed_golden_queries():
    """Create a default golden_queries.yaml template."""
    try:
        from core.harness.knowledge.wiki_structured_query import seed_golden_queries
        return {"status": seed_golden_queries()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {e}")


@router.post("/ontology/rebuild")
async def ontology_rebuild(collection: str = "default"):
    """Full rebuild of the knowledge ontology A-Box from current Wiki+KB data."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import rebuild_full
        onto = rebuild_full(collection_id=collection)
        return {"status": "rebuilt", "triples": len(onto.triples), "collection": collection}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {e}")


@router.get("/ontology/validate")
async def ontology_validate(collection: str = "default"):
    """Run all ontology axioms (A1-A7) against the current A-Box."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import validate as onto_validate
        
        onto = build_abox(collection_id=collection)
        report = onto_validate(onto)
        return {
            "timestamp": report.timestamp,
            "total_triples": report.total_triples,
            "violations": [
                {"axiom": v.axiom_id, "severity": v.severity,
                 "description": v.description, "recommendation": v.recommendation}
                for v in report.violations
            ],
            "score": report.score,
            "passed_axioms": report.passed_axioms,
            "failed_axioms": report.failed_axioms,
            "has_errors": report.has_errors,
            "collection": collection,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}")


@router.get("/ontology/network/{title:path}")
async def ontology_network(title: str, collection: str = "default"):
    """Get the transitive knowledge network from a starting Wiki page."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import query_transitive_network
        
        # Ensure A-Box is built for this collection
        build_abox(collection_id=collection)
        return query_transitive_network(title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Network query failed: {e}")


@router.get("/ontology/source-impact")
async def ontology_source_impact(collection: str = "default"):
    """Rank KB documents by how many Wiki pages cite them."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import query_source_impact
        
        # Ensure A-Box is built for this collection
        build_abox(collection_id=collection)
        return {"sources": query_source_impact()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Impact query failed: {e}")


@router.get("/wiki/changelog")
async def get_wiki_changelog():
    """Get recent wiki ingest changelog entries."""
    from core.harness.knowledge.wiki_engine import _wiki_root
    import json as _json
    root = _wiki_root()
    log_path = root / "changelog.json"
    if not log_path.exists():
        return {"entries": [], "total": 0}
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            entries = _json.load(f)
        return {"entries": entries[:20], "total": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read changelog: {e}")


@router.get("/wiki/duplicates")
async def detect_wiki_duplicates(collection: str = "default"):
    """Detect potentially duplicate wiki pages using embedding similarity."""
    try:
        from core.harness.knowledge.wiki_engine import detect_duplicate_pages
        duplicates = detect_duplicate_pages(collection_id=collection)
        return {"duplicates": duplicates, "total": len(duplicates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplicate detection failed: {e}")


# ── Collection Management ───────────────────────────────────────

@router.get("/collections")
async def list_wiki_collections():
    """List all wiki collections with page counts."""
    try:
        from core.harness.knowledge.wiki_engine import list_collections
        cols = list_collections()
        return {"collections": cols, "total": len(cols)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {e}")


@router.post("/collections")
async def create_wiki_collection(body: CollectionCreate):
    """Create a new wiki collection."""
    try:
        from core.harness.knowledge.wiki_engine import create_collection
        result = create_collection(body.collection_id)
        if result["status"] == "exists":
            return {"status": "ok", "message": f"Collection '{result['collection_id']}' already exists"}
        return {"status": "ok", "message": f"Collection '{result['collection_id']}' created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {e}")


@router.delete("/collections/{collection_id}")
async def delete_wiki_collection(collection_id: str):
    """Delete a wiki collection and all its pages."""
    try:
        from core.harness.knowledge.wiki_engine import delete_collection
        result = delete_collection(collection_id)
        if result["status"] == "protected":
            raise HTTPException(status_code=400, detail=result["reason"])
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")
        return {"status": "ok", "message": f"Collection '{collection_id}' deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete collection: {e}")


# ── Schema API ─────────────────────────────────────────────────

@router.get("/schema")
async def get_wiki_schema(collection: str = "default"):
    """Return T-Box class schemas, with per-collection extensions applied."""
    try:
        from core.harness.knowledge.knowledge_ontology import (
            get_classes_with_templates, get_extended_class,
            load_collection_extension, OBJECT_PROPERTIES, AI
        )
        extension = load_collection_extension(collection)
        schemas = []
        for cls in get_classes_with_templates():
            # Apply collection extension if applicable
            cat = cls.allowed_categories[0] if cls.allowed_categories else ""
            display_cls = get_extended_class(cat, collection) or cls
            props = []
            for op in OBJECT_PROPERTIES:
                if display_cls.uri in op.domain:
                    props.append({
                        "type": "relation",
                        "label": op.label,
                        "uri": op.uri,
                        "range": [r.replace(AI, "") for r in op.range],
                        "cardinality": {
                            "min": op.min_cardinality or 0,
                            "max": op.max_cardinality,
                        },
                        "is_transitive": op.is_transitive,
                        "is_symmetric": op.is_symmetric,
                    })
            schemas.append({
                "class_uri": display_cls.uri,
                "label": display_cls.label,
                "categories": display_cls.allowed_categories,
                "required_fields": display_cls.required_fields,
                "optional_fields": display_cls.optional_fields,
                "template_markdown": display_cls.template_markdown,
                "relations": props,
            })
        return {
            "schemas": schemas, "total": len(schemas),
            "collection": collection,
            "has_extension": extension is not None,
            "extension_label": extension.get("label", "") if extension else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load schemas: {e}")


@router.get("/ontology/classes")
async def list_ontology_classes():
    """Return T-Box class hierarchy for Agent query routing."""
    try:
        from core.harness.knowledge.knowledge_ontology import CLASSES, AI
        result = []
        for cls in CLASSES:
            children = [c.label for c in CLASSES if c.parent == cls.uri]
            result.append({
                "uri": cls.uri,
                "label": cls.label,
                "categories": cls.allowed_categories,
                "parent": cls.parent.replace(AI, "") if cls.parent else None,
                "children": children,
                "required_fields": getattr(cls, 'required_fields', []),
            })
        return {"classes": result, "total": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list classes: {e}")


# ── Inference Rules API ─────────────────────────────────────────

@router.get("/ontology/rules")
async def list_inference_rules():
    """List all inference rules (built-in + registered)."""
    try:
        from core.harness.knowledge.knowledge_validator import DEFAULT_RULES
        rules = [{
            "name": r.name, "description": r.description,
            "trigger": r.trigger.value, "enabled": r.enabled,
            "severity": r.severity,
        } for r in DEFAULT_RULES]
        return {"rules": rules, "total": len(rules)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list rules: {e}")


@router.post("/ontology/rules")
async def register_inference_rule(body: Dict[str, Any]):
    """Register a custom inference rule."""
    try:
        from core.harness.knowledge.knowledge_validator import (
            InferenceRule, RuleTrigger, register_rule
        )
        trigger = body.get("trigger", "on_create")
        if trigger not in [t.value for t in RuleTrigger]:
            raise HTTPException(status_code=400,
                detail=f"Invalid trigger. Must be one of {[t.value for t in RuleTrigger]}")
        rule = InferenceRule(
            name=body["name"],
            description=body.get("description", ""),
            trigger=RuleTrigger(trigger),
            pattern=body.get("pattern", ""),
            action=body.get("action", ""),
            severity=body.get("severity", "warning"),
        )
        register_rule(rule)
        return {"status": "registered", "name": rule.name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register rule: {e}")


# ── Evidence Chain API (Phase 4) ──────────────────────────────────

@router.get("/claim/{title}/evidence-chain")
async def get_claim_evidence_chain(title: str, collection: str = "default"):
    """Return full evidence chain for a Wiki claim/atom.

    Chain: page → source documents → contradictions → resolutions.
    """
    try:
        from core.harness.knowledge.wiki_engine import read_page, search_pages
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import TripleStore, _short

        page = read_page(title, collection_id=collection)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page '{title}' not found")

        # 1. Direct source evidence
        source_articles = page.get("source_articles", [])
        evidence_text = None
        # Check if this is an atom page with evidence_text in frontmatter
        fm = page.get("fm", {})
        if fm.get("source_doc_id"):
            evidence_text = fm.get("evidence_text", "")
            source_articles = [fm["source_doc_id"]]
        # Fallback: evidence_text may be in summary field (write_atom stores it there)
        if not evidence_text:
            evidence_text = fm.get("evidence_text") or page.get("summary", "") or None
        # Parse evidence metadata from body HTML comments
        body = page.get("body", "")
        evidence_meta = {}
        import re as _re
        for m in _re.finditer(r'<!--\s*(source_doc_id|evidence_start|evidence_end|confidence):\s*([\d.]+[^\s-]*)\s*-->', body):
            key, val = m.group(1), m.group(2)
            try:
                evidence_meta[key] = float(val) if key in ("confidence", "evidence_start", "evidence_end") else val
            except ValueError:
                evidence_meta[key] = val
        if evidence_meta.get("source_doc_id") and not source_articles:
            source_articles = [evidence_meta["source_doc_id"]]

        # 2. Contradictions and related pages
        contradictions = page.get("contradictions", [])
        related = page.get("related", [])

        # 3. Ontology-level contradictions (from A-Box)
        onto = build_abox(collection_id=collection)
        store = TripleStore(onto.triples)
        onto_contradictions = [
            _short(c) for c in store.objects(f"http://aiplat.local/knowledge#{title}",
                                              "http://aiplat.local/knowledge#contradicts")
        ]

        # 4. Stale references
        stale = page.get("stale_references", [])

        return {
            "claim": title,
            "source_articles": source_articles,
            "evidence_text": evidence_text,
            "contradictions": contradictions,
            "onto_contradictions": [c for c in onto_contradictions if c != title],
            "related": related,
            "stale_references": stale,
            "has_controversy": len(contradictions) > 0 or len(onto_contradictions) > 1,
            "category": page.get("category", ""),
            "last_updated": page.get("last_updated", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence chain failed: {e}")


# ── OWL/RDF Export (Phase 5) ─────────────────────────────────────

@router.get("/ontology/export")
async def export_ontology_rdf(format: str = "turtle", collection: str = "default"):
    """Export T-Box + A-Box as OWL/RDF.

    Supported formats: turtle (default), rdfxml, ntriples.
    Compatible with Protégé, GraphDB, Stardog, and other semantic web tools.
    """
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_ontology import export_to_owl_rdf

        build_abox(collection_id=collection)
        rdf_text = export_to_owl_rdf(format=format)

        content_types = {
            "turtle": "text/turtle",
            "rdfxml": "application/rdf+xml",
            "ntriples": "application/n-triples",
        }
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(rdf_text, media_type=content_types.get(format, "text/plain"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.get("/ontology/infer")
async def run_inference_engine(collection: str = "default"):
    """Run full inference engine and return suggested edges."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import (
            TripleStore, run_full_inference, _short
        )
        onto = build_abox(collection_id=collection)
        store = TripleStore(onto.triples)
        inference = run_full_inference(store)

        suggestions = []
        for kind in ("transitive", "source_chain"):
            for inf in inference.get(kind, []):
                suggestions.append({
                    "kind": kind,
                    "from": _short(inf["subject"]),
                    "relation": inf["predicate"].replace("http://aiplat.local/knowledge#", ""),
                    "to": _short(inf["object"]),
                })

        return {
            "summary": inference.get("summary", ""),
            "suggestions": suggestions,
            "total": len(suggestions),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")


# ── Pattern Detector (Ontology Evolution Layer 1) ─────────────────

@router.get("/ontology/patterns")
async def detect_patterns(collection: str = "default"):
    """Scan wiki data and detect patterns not yet covered by T-Box.

    Returns:
    - undefined_categories: categories used in wiki but not in any T-Box class
    - tag_clusters: high-frequency tags that may warrant new ontology classes
    - dangling_references: pages referencing titles that don't exist (with variant suggestions)
    - category_gaps: T-Box classes with zero wiki pages
    - undefined_relations: relationship types in pages not in OBJECT_PROPERTIES
    """
    try:
        from core.harness.knowledge.knowledge_validator import detect_ontology_patterns
        patterns = detect_ontology_patterns(collection_id=collection)
        return {
            "summary": patterns.summary,
            "scanned_pages": patterns.scanned_pages,
            "scanned_collections": patterns.scanned_collections,
            "undefined_categories": patterns.undefined_categories,
            "undefined_relations": patterns.undefined_relations,
            "tag_clusters": patterns.tag_clusters,
            "dangling_references": patterns.dangling_references,
            "category_gaps": patterns.category_gaps,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pattern detection failed: {e}")


@router.get("/ontology/metrics")
async def get_ontology_metrics(collection: str = "default", refresh: bool = False):
    """Four-dimension ontology health metrics (with hourly cache).

    Dimensions:
    1. Coverage: % wiki pages covered by T-Box classes
    2. Consistency: validator errors / warnings / score
    3. Inference gain: transitive + source_chain edges inferred
    4. Maintenance cost: pending suggestions + last review time
    Class usage: per-class wiki page counts
    """
    try:
        from core.harness.knowledge.knowledge_validator import (
            compute_ontology_metrics, load_metrics_cache
        )
        if not refresh:
            cached = load_metrics_cache(collection)
            if cached and "metrics" in cached:
                return {"source": "cache", **cached["metrics"]}

        metrics = compute_ontology_metrics(collection_id=collection, force_fresh=True)
        return {"source": "computed", **metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics failed: {e}")


@router.get("/ontology/metrics/history")
async def get_metrics_history(collection: str = "default"):
    """Return historical metrics snapshots for trend analysis (last 30 days)."""
    try:
        from core.harness.knowledge.knowledge_validator import load_metrics_history
        history = load_metrics_history(collection)
        return {"history": history, "total": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History failed: {e}")


@router.get("/ontology/golden-regression")
async def run_golden_regression(collection: str = "default", min_score: float = None, strict: bool = False):
    """Run golden query regression test to validate retrieval quality.

    Uses golden_queries.yaml (8 queries) to check whether wiki retrieval
    returns expected concepts. Returns pass rate and per-query details.

    Args:
        min_score: Custom min_wiki_score threshold (overrides strict).
        strict: Use production threshold (0.3) instead of test threshold (0.1).
    """
    try:
        from core.harness.knowledge.knowledge_validator import run_golden_query_regression
        result = run_golden_query_regression(collection_id=collection, min_score=min_score, strict_mode=strict)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regression failed: {e}")


# ── Ontology Suggestions (Layer 3) ───────────────────────────────

@router.get("/ontology/suggestions")
async def list_suggestions(status: str = "", collection: str = "default"):
    """List ontology evolution suggestions."""
    try:
        from core.harness.knowledge.knowledge_ontology import load_pending_suggestions
        suggestions = load_pending_suggestions(collection)
        if status:
            suggestions = [s for s in suggestions if s.get("status") == status]
        return {"suggestions": suggestions, "total": len(suggestions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list suggestions: {e}")


@router.post("/ontology/suggestions")
async def generate_suggestions(collection: str = "default"):
    """Scan wiki data and generate ontology evolution suggestions."""
    try:
        from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
        suggestions = add_suggestions_from_patterns(collection_id=collection)
        pending = [s for s in suggestions if s.get("status") == "pending"]
        return {"status": "generated", "total": len(suggestions), "pending": len(pending)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suggestion generation failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: str, reviewer: str = "", collection: str = "default"):
    """Accept an ontology evolution suggestion (marks for implementation)."""
    try:
        from core.harness.knowledge.knowledge_ontology import accept_suggestion
        result = accept_suggestion(suggestion_id, reviewer=reviewer, collection_id=collection)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found")
        return {"status": "accepted", "suggestion": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Accept failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: str, reason: str = "", reviewer: str = "", collection: str = "default"):
    """Reject an ontology evolution suggestion."""
    try:
        from core.harness.knowledge.knowledge_ontology import reject_suggestion
        result = reject_suggestion(suggestion_id, reason=reason, reviewer=reviewer, collection_id=collection)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found")
        return {"status": "rejected", "suggestion": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reject failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/generate-code")
async def generate_code(suggestion_id: str, collection: str = "default"):
    """Generate implementation code for an accepted suggestion."""
    try:
        from core.harness.knowledge.knowledge_ontology import generate_code_for_suggestion
        result = generate_code_for_suggestion(suggestion_id, collection_id=collection)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {e}")


@router.get("/ontology/schema-readiness")
async def check_schema_readiness(collection: str = "default"):
    """Check how many wiki pages would pass ERROR-mode schema validation.

    Returns readiness percentage and list of failing pages with missing fields.
    Use this before enabling AIPLAT_WIKI_SCHEMA_MODE=error.
    """
    try:
        from core.harness.knowledge.knowledge_ontology import check_schema_readiness
        return check_schema_readiness(collection_id=collection)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Readiness check failed: {e}")


@router.post("/clean-stale-references")
async def clean_stale_references_endpoint(collection: str = "default"):
    """Scan wiki pages, move stale kb: references from source_articles to stale_references.

    A reference is stale when the kb:doc_id does not exist in the KB database.
    After cleanup, the A-Box is rebuilt to refresh validator consistency scores.
    """
    try:
        from core.harness.knowledge.wiki_engine import clean_stale_references
        result = clean_stale_references(collection_id=collection)
        return {
            "status": "completed",
            "scanned": result["scanned"],
            "affected_pages": result["affected"],
            "stale_refs_moved": result["stale_refs_moved"],
            "abox_rebuilt": result.get("abox_rebuilt", False),
            "details": result.get("details", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {e}")


@router.post("/seed-instances")
async def seed_instances_endpoint(collection: str = "default"):
    """Create seed instances for empty T-Box categories (atoms, contradictions).

    Scans topic pages for sub-concepts (→ atom pages) and contradictory
    page pairs (→ contradiction pages). Uses LLM for content analysis.
    """
    try:
        from core.harness.knowledge.wiki_engine import seed_instances
        result = await seed_instances(collection_id=collection)
        return {
            "status": "completed",
            "atoms_created": result["atoms_created"],
            "contradictions_created": result["contradictions_created"],
            "details": result.get("details", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seeding failed: {e}")


@router.post("/backfill-evidence")
async def backfill_evidence_endpoint(limit: int = 50, collection: str = "default"):
    """Backfill evidence annotations for wiki pages without them.

    Extracts the first 1-2 sentences from each page as evidence_text,
    embedding them as HTML comments for the evidence-chain API.
    """
    try:
        from core.harness.knowledge.wiki_engine import backfill_evidence_batch_sync
        result = backfill_evidence_batch_sync(collection_id=collection, limit=limit)
        return {
            "status": "completed",
            "candidates": result["total_candidates"],
            "succeeded": result["succeeded"],
            "failed": result["failed"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backfill failed: {e}")


@router.post("/batch-atomize")
async def batch_atomize_endpoint(limit: int = 10, category: str = "topics", collection: str = "default"):
    """Batch atomize pages of a given category using LLM sub-concept extraction.

    Rate limited to 1 request/second. Creates KnowledgeAtom pages from
    topic page content.
    """
    import asyncio
    try:
        from core.harness.knowledge.wiki_engine import (
            search_pages, read_page, write_atom, _extract_sub_concepts
        )
        pages = [p for p in search_pages(limit=1000, collection_id=collection)
                 if p.get("category") == category]
        created = 0
        for page in pages[:limit]:
            full = read_page(page["title"], collection_id=collection)
            if full and len(full.get("body", "")) > 500:
                atoms = await _extract_sub_concepts(
                    page["title"], full["body"], collection
                )
                for atom in atoms[:2]:
                    existing = read_page(atom["title"], collection_id=collection)
                    if not existing:
                        write_atom(atom, collection_id=collection)
                        created += 1
                await asyncio.sleep(1.0)
        return {"status": "completed", "atoms_created": created, "scanned": min(limit, len(pages))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch atomize failed: {e}")


@router.post("/maintain/fts-rebuild")
async def rebuild_fts_index(collection: str = "default"):
    """Rebuild FTS5 full-text search index for wiki pages."""
    try:
        from core.harness.knowledge.wiki_fts import fts_index_pages
        count = fts_index_pages()
        return {"status": "completed", "indexed": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FTS rebuild failed: {e}")


@router.post("/wiki/evolve")
async def evolve_knowledge(collection: str = "default", generations: int = 1,
                            max_mutations: int = 5, force: bool = False):
    """Run knowledge evolution — event-driven, not timer-driven.

    Triggers:
      - New pages >= 3 since last gen (auto, from wiki_auto_update)
      - Golden pass_rate dropped >= 10% (auto, from metrics)
      - force=True (manual, from frontend)
    
    Uses local LLM (qwen2.5:7b) for zero API cost.
    """
    try:
        from core.harness.knowledge.evolution_runner import EvolutionRunner
        runner = EvolutionRunner(
            collection_id=collection,
            max_mutations=max_mutations,
        )
        results = []
        for _ in range(generations):
            result = await runner.run_one_generation()
            results.append(result)
            if result.get("verdict") == "SKIPPED":
                if not force:
                    break
        return {"generations": results, "collection": collection}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evolution failed: {e}")


@router.get("/wiki/evolution-history")
async def get_evolution_history(collection: str = "default"):
    """Get evolution generation history."""
    import json as _json, os as _os
    hist_path = _os.path.join(
        _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat")),
        "wiki", "collections", collection, "evolution_history.json")
    if not _os.path.exists(hist_path):
        return {"generations": [], "total": 0}
    try:
        history = _json.loads(open(hist_path).read())
        return {"generations": history, "total": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/maintain/model-log")
async def get_model_selection_log():
    """Return recent model selection log entries."""
    try:
        import json, os
        log_path = os.path.expanduser("~/.aiplat/wiki/model_selection_log.json")
        if not os.path.exists(log_path):
            return {"entries": [], "total": 0}
        entries = json.loads(open(log_path).read())
        return {"entries": entries[-50:], "total": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
