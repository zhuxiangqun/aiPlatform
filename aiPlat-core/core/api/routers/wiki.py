"""
Wiki API — persistent LLM-curated knowledge base endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/wiki", tags=["wiki"])


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
async def convert_from_kb(tenant_id: str = "default", collection_id: str = "default", limit: int = 50):
    u"""Convert existing KB documents into Wiki pages.
    
    Reads documents from the RAG knowledge base (SQLite), extracts titles and
    full text, and creates initial Wiki entity pages. Auto-detects related pages
    by shared keywords.
    """
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
                    write_page(curated["title"], body,
                        category=curated.get("category", "entities"),
                        tags=curated.get("tags", tags),
                        related=curated.get("related", []),
                        summary=curated.get("summary", summary),
                        source_articles=[f"kb:{doc_id}"])
                    # Create entity pages
                    for entity in curated.get("entities_found", [])[:5]:
                        safe_entity = re.sub(r"[<>:\"/\\|?*]", "_", entity)[:120]
                        if safe_entity != safe_title and safe_entity not in topic_keywords:
                            write_page(safe_entity, f"Entity: {entity}\n\nSee: [[{safe_title}]]",
                                category="entities", tags=[entity.lower()], related=[safe_title])
                            entities_created += 1
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
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    wiki_pages = meta.get("wiki_pages", [])
                    if safe_title not in wiki_pages:
                        wiki_pages.append(safe_title)
                        meta["wiki_pages"] = wiki_pages
                        conn.execute("UPDATE documents SET meta_json=? WHERE doc_id=? AND tenant_id=?",
                                    (_json.dumps(meta, ensure_ascii=False), doc_id, tenant_id))
                        conn.commit()
                except Exception as e:
                    writeback_errors += 1
                    logger.warning(f"convert-from-kb: failed to write wiki_pages for doc {doc_id}: {e}")

            # Cross-link pages that share keywords
            for kw, titles in topic_keywords.items():
                if len(titles) >= 2:
                    for t in titles:
                        related = [t2 for t2 in titles if t2 != t]
                        # Update each page's related links
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

    # Also scan uploads/ directory for files not yet in wiki
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
                    update_page(p["title"], related=list(set(
                        (p.get("related") or []) + auto_rel
                    )))
                    report["links_added"] += len(auto_rel)
                    report["processed"] += 1
                continue

            update_page(p["title"],
                        title=result.get("title"),
                        category=result.get("category"),
                        tags=result.get("tags"),
                        summary=result.get("summary"),
                        related=list(set(
                            (p.get("related") or []) + result.get("related", [])
                        )))
            report["processed"] += 1
            report["links_added"] += len(result.get("related", []))
            if result.get("title") != p["title"]:
                report["titles_updated"] += 1
        except Exception as e:
            report["errors"].append({"page": p["title"], "error": str(e)[:300]})

    return report
