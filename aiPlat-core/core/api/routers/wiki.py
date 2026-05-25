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
