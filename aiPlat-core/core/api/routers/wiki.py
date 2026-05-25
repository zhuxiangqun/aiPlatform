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
    return {"items": pages, "total": len(pages)}


@router.get("/pages/{title}")
async def read_page(title: str, category: str = "entities"):
    from core.harness.knowledge.wiki_engine import read_page
    page = read_page(title, category=category)
    if not page:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")
    return page


@router.post("/pages")
async def write_page(body: WikiPageWrite):
    from core.harness.knowledge.wiki_engine import write_page
    path = write_page(body.title, body.body, category=body.category,
                      tags=body.tags, related=body.related, summary=body.summary)
    return {"title": body.title, "path": path, "status": "created"}


@router.get("/traverse/{title}")
async def traverse_links(title: str, depth: int = 2):
    from core.harness.knowledge.wiki_engine import traverse_links
    pages = traverse_links(title, depth=depth)
    return {"root": title, "depth": depth, "pages": len(pages), "items": pages}


@router.get("/lint")
async def lint_wiki():
    from core.harness.knowledge.wiki_engine import detect_contradictions
    issues = detect_contradictions()
    return {"issues": issues, "total": len(issues),
            "health_score": max(0, 100 - len(issues) * 5)}


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
    """Convert existing KB documents into Wiki pages.
    
    Reads documents from the RAG knowledge base (SQLite), extracts titles and
    full text, and creates initial Wiki entity pages. Auto-detects related pages
    by shared keywords.
    """
    import os, re, time as _time
    from core.harness.knowledge.wiki_engine import write_page, _wiki_root

    created = 0
    skipped = 0
    errors = []

    try:
        # Read KB documents from platform KB storage
        kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
        kb_db = os.path.join(kb_dir, tenant_id, "kb.sqlite3")
        if not os.path.exists(kb_db):
            return {"created": 0, "skipped": 0, "errors": ["KB database not found. Ensure documents are ingested into the knowledge base first."]}

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
                return {"created": 0, "skipped": 0, "errors": ["No documents found in KB. Ingest documents first via Knowledge Base page."]}

            topic_keywords = {}  # Track shared keywords across documents for cross-linking

            for doc in docs:
                doc_id = doc["doc_id"]
                source_uri = str(doc.get("source_uri", doc_id) or doc_id)
                # Extract title from filename or meta
                title = os.path.basename(source_uri).rsplit(".", 1)[0][:100] or doc_id[:60]
                # Try to get title from meta_json
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    if meta.get("title"):
                        title = str(meta["title"])[:120]
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
                write_page(safe_title, body, category="entities", tags=tags, summary=summary)
                created += 1

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

    return {"created": created, "skipped": skipped, "errors": errors,
            "message": f"Converted {created} KB documents to Wiki pages. {skipped} skipped."}
