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


@router.get("/pages")
async def list_pages(
    category: str = "",
    tag: str = "",
    query: str = "",
    source: str = "",
    limit: int = 100,
    offset: int = 0,
):
    from core.harness.knowledge.wiki_engine import search_pages, list_all_pages
    if query or tag:
        tags = [tag] if tag else None
        pages = search_pages(query=query, tags=tags, category=category, limit=limit)
    else:
        pages = list_all_pages()
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
async def read_page(title: str, category: str = "entities"):
    from core.harness.knowledge.wiki_engine import read_page
    page = read_page(title, category=category)
    if not page:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")
    return page


@router.delete("/pages/{title}")
async def delete_page(title: str):
    from core.harness.knowledge.wiki_engine import delete_page as _del
    ok = _del(title)
    if not ok:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")
    return {"title": title, "status": "deleted"}


@router.delete("/pages-all")
async def delete_all_pages():
    from core.harness.knowledge.wiki_engine import delete_all_pages
    result = delete_all_pages()
    return {"deleted": result["deleted"], "message": f"已清空 {result['deleted']} 个 Wiki 页面"}


@router.get("/unprocessed-docs")
async def get_unprocessed_docs(tenant_id: str = "default"):
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
    wiki_pages = search_pages(limit=1000)
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
async def get_proposals(status: str = ""):
    u"""List pending wiki knowledge proposals (merge/update/supplement/contradict)."""
    from core.harness.knowledge.wiki_engine import load_proposals
    proposals = load_proposals()
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return {"items": proposals, "total": len(proposals)}


@router.put("/proposals/{proposal_id}")
async def handle_proposal(proposal_id: str, body: Dict[str, Any]):
    u"""Approve/reject a proposal. Body: {status: 'approved'|'rejected'}."""
    from core.harness.knowledge.wiki_engine import update_proposal_status, apply_proposal
    status = body.get("status", "")
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")
    ok = update_proposal_status(proposal_id, status)
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    result = {"proposal_id": proposal_id, "status": status}
    # If approved, execute the proposal action
    if status == "approved":
        result["execution"] = apply_proposal(proposal_id)
    return result


@router.post("/pages")
async def write_page(body: WikiPageWrite):
    from core.harness.knowledge.wiki_engine import write_page, auto_link_page, search_pages, update_page
    path = write_page(body.title, body.body, category=body.category,
                      tags=body.tags, related=body.related, summary=body.summary)
    # Auto-link via embedding similarity (through infra adapter)
    auto_links = []
    try:
        all_titles = [p["title"] for p in search_pages(limit=500)]
        auto_links = auto_link_page(body.title, body.body, all_titles)
        if auto_links:
            update_page(body.title, related=list(set(body.related or [] + auto_links)))
    except Exception:
        pass
    return {"title": body.title, "path": path, "status": "created", "auto_links": auto_links}


@router.get("/traverse/{title}")
async def traverse_links(title: str, depth: int = 2):
    from core.harness.knowledge.wiki_engine import traverse_links
    pages = traverse_links(title, depth=depth)
    return {"root": title, "depth": depth, "pages": len(pages), "items": pages}


@router.get("/lint")
async def lint_wiki():
    from core.harness.knowledge.wiki_engine import wiki_health_report
    return wiki_health_report()


@router.get("/graph")
async def wiki_graph(
    category: str = "",
    keyword: str = "",
    source: str = "",
    max_nodes: int = 300,
):
    from core.harness.knowledge.wiki_engine import build_graph
    return build_graph(category=category, keyword=keyword, source=source, max_nodes=max_nodes)


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


@router.post("/convert-from-kb")
async def convert_from_kb(req: ConvertKbRequest = Body(default=None)):
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
                          source_articles=[f"kb:{doc_id}"])
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
                        source_articles=[f"kb:{doc_id}"])
                    # If LLM changed the title, delete the mechanically-created page
                    if curated["title"] != old_title:
                        from core.harness.knowledge.wiki_engine import delete_page as _delp
                        try: _delp(old_title)
                        except: pass
                    # Always delete the mechanical page if it still exists
                    from core.harness.knowledge.wiki_engine import delete_page as _delp2
                    try: _delp2(old_title)
                    except: pass
                    # Create knowledge atom pages
                    for atom in curated.get("knowledge_atoms", [])[:8]:
                        if not atom.get("title") or not atom.get("body"):
                            continue
                        atom_title = re.sub(r"[<>:\"/\\|?*]", "_", str(atom["title"])[:80])
                        atom_body = str(atom["body"])[:20000]
                        atom_tags = list(atom.get("tags", []))[:5]
                        atom_cat = str(atom.get("category", "entities"))
                        if atom_title and atom_title != curated["title"]:
                            write_page(atom_title, atom_body,
                                category=atom_cat,
                                tags=atom_tags,
                                related=list(set([curated["title"]] + curated.get("related", [])[:3])),
                                summary=atom_body[:300].replace("\n", " "),
                                source_articles=[f"kb:{doc_id}"])
                            entities_created += 1
                    # After creating knowledge atoms, update main page's related
                    # to include them (prevent orphan pages)
                    if entities_created > 0 and curated.get("title"):
                        main_page = read_page(curated["title"])
                        if main_page:
                            atom_titles = []
                            for atom in curated.get("knowledge_atoms", [])[:8]:
                                a_title = re.sub(r"[<>:\"/\\|?*]", "_", str(atom.get("title", ""))[:80])
                                if a_title and a_title != curated["title"]:
                                    atom_titles.append(a_title)
                            if atom_titles:
                                existing_related = set(main_page.get("related", []) or [])
                                existing_related.update(atom_titles)
                                write_page(curated["title"], main_page.get("body", ""),
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
                            write_page(con.get("b", ""), old_page.get("body", ""),
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
                        conn.execute("UPDATE documents SET meta_json=? WHERE doc_id=? AND tenant_id=?",
                                    (_json.dumps(meta, ensure_ascii=False), doc_id, tenant_id))
                        conn.commit()
                except Exception as e:
                    writeback_errors += 1
                    logger.warning(f"convert-from-kb: failed to write wiki_pages for doc {doc_id}: {e}")

            # Cross-link pages that share keywords (validate against actual existing pages)
            valid_titles = set()
            try:
                from core.harness.knowledge.wiki_engine import search_pages
                valid_titles = set(p["title"] for p in (search_pages(limit=1000) or []))
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
                        page = read_page(t, category="entities")
                        if page:
                            existing = set(page.get("related", []))
                            existing.update(related[:5])
                            write_page(t, page.get("body", ""), category="entities",
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
                existing_wiki = set(p["title"] for p in search_pages(limit=1000))

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
                              source_articles=[f"upload:{fname}"])
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
async def curate_wiki():
    u"""LLM 深度策展：遍历所有 Wiki 页面，用 LLM 重写标题/分类/标签/摘要/关联。

    返回: {processed, links_added, titles_updated, errors[]}
    如果 LLM 不可用，降级到嵌入自动关联。
    """
    from core.harness.knowledge.wiki_engine import search_pages, llm_curate_page, update_page, auto_link_page
    pages = search_pages(limit=500)
    report = {"processed": 0, "links_added": 0, "titles_updated": 0, "errors": []}
    all_titles = [p["title"] for p in pages]

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
                    save_proposal({
                        "action": "merge",
                        "from_title": p["title"],
                        "to_title": mc["target"],
                        "reason": str(mc.get("reason", "content overlap")),
                        "source_doc": "",
                        "status": "pending",
                        "created_at": str(int(_t.time())),
                    })
            for con in result.get("contradictions", [])[:3]:
                b_title = con.get("b", "") if isinstance(con, dict) else con
                if b_title and b_title in existing_titles:
                    from core.harness.knowledge.wiki_engine import save_proposal
                    save_proposal({
                        "action": "contradict",
                        "from_title": p["title"],
                        "to_title": b_title,
                        "reason": str(con.get("detail", "conflicting claims") if isinstance(con, dict) else "conflicting claims"),
                        "source_doc": "",
                        "status": "pending",
                        "created_at": str(int(_t.time())),
                    })
        except Exception as e:
            report["errors"].append({"page": p["title"], "error": str(e)[:300]})

    return report
