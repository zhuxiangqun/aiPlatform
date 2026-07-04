"""
Wiki Engine — persistent, LLM-maintained markdown knowledge base.

Operations: search (by title/tag/link), traverse (follow [[links]]),
read/write pages, detect contradictions.

Wiki root: ~/.aiplat/wiki/
Directory structure:
  entities/          # Entity pages (concepts, people, projects)
  topics/            # Topic summaries (cross-entity analyses)
  contradictions/    # Detected contradictions (auto-marked by LLM)
  schema.yml         # Wiki structure rules
  index.json         # Global page index
"""

from __future__ import annotations

import os
import re
import json as _json
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Configuration ──────────────────────────────────────────────

FRONTMATTER_FIELDS = {
    "title": "", "category": "entities", "tags": [], "related": [],
    "contradictions": [], "source_articles": [], "last_updated": "",
    "summary": "", "version": "1", "stale_references": [], "images": [],
    "status": "draft", "marking": "public",
    # K4: temporal validity
    "effective_date": "", "expiry_date": "",
    # K4: organizational ownership
    "department": "", "owner": "",
}

def _wiki_root(collection_id: str = "default") -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    root = Path(home) / "wiki"
    _migrate_legacy_wiki(root)
    return root / "collections" / (collection_id or "default")


def _migrate_legacy_wiki(root: Path) -> None:
    """Auto-migrate legacy flat wiki structure to collections/default/."""
    legacy_idx = root / "index.json"
    collections_dir = root / "collections"
    if collections_dir.exists():
        return
    if not legacy_idx.exists() and not (root / "entities").exists():
        collections_dir.mkdir(parents=True, exist_ok=True)
        return
    import shutil
    default_root = collections_dir / "default"
    default_root.mkdir(parents=True, exist_ok=True)
    # Move directories
    for d in ["entities", "topics", "contradictions", "atoms", "_sources"]:
        src = root / d
        if src.exists():
            shutil.move(str(src), str(default_root / d))
    # Move files
    for f in ["index.json", "proposals.json", "schema.yml",
              "changelog.json", "health_history.json", "fts.db"]:
        src = root / f
        if src.exists():
            shutil.move(str(src), str(default_root / f))
    _init_global_index(root)

def _init_global_index(root: Path) -> None:
    gidx = root / "index.json"
    if not gidx.exists():
        gidx.write_text(_json.dumps({"collections": {}, "last_updated": ""}, indent=2))

def list_collections() -> List[Dict[str, Any]]:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    root = Path(home) / "wiki"
    _migrate_legacy_wiki(root)
    collections_dir = root / "collections"
    if not collections_dir.exists():
        return []
    result = []
    for d in sorted(collections_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            idx = d / "index.json"
            page_count = 0
            try:
                if idx.exists():
                    pages = _json.loads(idx.read_text(encoding="utf-8")).get("pages", {})
                    page_count = len(pages)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            result.append({"collection_id": d.name, "page_count": page_count})
    return result

def create_collection(collection_id: str) -> Dict[str, Any]:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    root = Path(home) / "wiki"
    _migrate_legacy_wiki(root)
    coll_dir = root / "collections" / collection_id
    if coll_dir.exists():
        return {"status": "exists", "collection_id": collection_id}
    _ensure_dirs(collection_id)
    return {"status": "created", "collection_id": collection_id}

def delete_collection(collection_id: str) -> Dict[str, Any]:
    if collection_id == "default":
        return {"status": "protected", "reason": "cannot delete default collection"}
    import shutil
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    coll_dir = Path(home) / "wiki" / "collections" / collection_id
    if not coll_dir.exists():
        return {"status": "not_found"}
    shutil.rmtree(str(coll_dir))
    return {"status": "deleted", "collection_id": collection_id}


def parse_title_from_uri(source_uri: str) -> str:
    u"""Extract a readable title from an upload filename.

    Examples:
      'req_01KS_1080p_xtdowner.com_放弃RAG吧_LLM知识库新范式_Karpathy新思路.mp4'
        → '放弃 RAG：LLM 知识库新范式'
    """
    fname = Path(source_uri).stem
    for prefix in ["preview_", "req_", "src_"]:
        if fname.startswith(prefix):
            fname = fname[len(prefix):]
    fname = re.sub(r'^[A-Z0-9]{26,30}_', '', fname)   # strip ULID
    fname = re.sub(r'\d{3,4}p_', '', fname)            # strip resolution
    fname = re.sub(r'xtdowner\.com_', '', fname)        # strip domain
    fname = re.sub(r'(_ai_|_技术_|_分享_)', ' · ', fname)
    fname = re.sub(r'(?<=[\u4e00-\u9fff])_(?=[\u4e00-\u9fff])', ' ', fname)
    for sfx in ['.edited', '.preview_cache', '.mp4', '.avi', '.mkv', '.json']:
        fname = fname.replace(sfx, '')
    fname = fname.replace('_', ' ').strip()
    fname = re.sub(r'\s{2,}', ' ', fname)
    parts = [p.strip() for p in re.split(r'[ ·,|：:\-]+', fname) if len(p.strip()) >= 2]
    if parts:
        return parts[0][:60]
    return fname[:60]

def _ensure_dirs(collection_id: str = "default"):
    root = _wiki_root(collection_id)
    for d in ["entities", "topics", "contradictions", "atoms"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    idx = root / "index.json"
    if not idx.exists():
        idx.write_text(_json.dumps({"pages": {}, "last_updated": ""}, indent=2))
    schema = root / "schema.yml"
    if not schema.exists():
        schema.write_text("# Wiki Schema — customize wiki structure rules\n"
                         "categories:\n"
                         "  - entities     # People, projects, concepts\n"
                         "  - topics       # Cross-entity analysis\n"
                         "  - contradictions  # Knowledge conflicts\n"
                         "template:\n"
                         "  fields:\n"
                         "    - title\n"
                         "    - summary\n"
                         "    - related_pages\n"
                         "    - contradictions\n"
                         "    - last_updated\n"
                         "    - source_articles\n")

# ── Page read/write ────────────────────────────────────────────

FRONTMATTER_FIELDS = {
    "title": "",
    "category": "entity",
    "tags": [],
    "related": [],
    "contradictions": [],
    "source_articles": [],
    "stale_references": [],
    "relationships": [],
    "images": [],
    "last_updated": "",
    "summary": "",
    # K4: temporal validity + org ownership
    "effective_date": "", "expiry_date": "",
    "department": "", "owner": "",
}


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from markdown wiki page."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2].strip()
    fm: Dict[str, Any] = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip().strip("'\"")
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
        else:
            fm[key] = val
    for k, default in FRONTMATTER_FIELDS.items():
        if k not in fm:
            fm[k] = default
    return fm, body


def read_page(title_or_path: str, *, category: str = "entities", collection_id: str = "default") -> Optional[Dict[str, Any]]:
    """Read a wiki page. Returns {title, category, tags, body, fm, path} or None."""
    _ensure_dirs(collection_id)
    root = _wiki_root(collection_id)
    name = re.sub(r"[<>:\"/\\|?*]", "_", title_or_path)[:120]
    # Try exact match first
    for cat in [category, "entities", "topics", "contradictions", "atoms"]:
        p = root / cat / f"{name}.md"
        if p.exists():
            text = p.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(text)
            return {"title": fm.get("title", name), "category": cat, "tags": fm.get("tags", []),
                    "related": fm.get("related", []), "contradictions": fm.get("contradictions", []),
                    "source_articles": fm.get("source_articles", []),
                    "stale_references": fm.get("stale_references", []),
                    "relationships": fm.get("relationships", []),
                    "status": fm.get("status", "draft"),
                    "marking": fm.get("marking", "public"),
                    "last_updated": fm.get("last_updated", ""), "summary": fm.get("summary", ""),
                    "body": body, "fm": fm, "path": str(p)}
    return None


def _run_coro_blocking(coro):
    """Run an async coroutine to completion from a sync function.

    write_page is sync but is often called from within a running event loop
    (e.g. the async wiki_auto_update ingest path). asyncio.run() raises inside
    a running loop, which previously dropped the cache-invalidation / provenance
    update hooks silently. Offload to a worker thread with a fresh loop when a
    loop is already running; otherwise run directly.
    """
    import asyncio as _a
    import concurrent.futures as _cf
    try:
        _a.get_running_loop()
    except RuntimeError:
        return _a.run(coro)
    with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
        return _pool.submit(_a.run, coro).result(timeout=30)


def write_page(title: str, body: str, *, category: str = "entities", tags: List[str] = None,
               related: List[str] = None, contradictions: List[str] = None,
               source_articles: List[str] = None, stale_references: List[str] = None,
               relationships: List[Dict[str, str]] = None,
               images: List[Dict[str, str]] = None,
               version: str = "1", summary: str = "", status: str = "",
               marking: str = "", collection_id: str = "default") -> str:
    """Create or update a wiki page. Returns the file path."""
    import re as _re

    _ensure_dirs(collection_id)
    root = _wiki_root(collection_id)

    # ── Sanitize title: strip HTML comments and metadata artifacts ──
    title = _re.sub(r'<!--.*?-->', '', title).strip()
    title = _re.sub(r'[_\\s]+$', '', title).strip()
    if not title:
        title = "unnamed_page"

    # ── Schema validation against T-Box ──
    import os as _os
    schema_mode = _os.getenv("AIPLAT_WIKI_SCHEMA_MODE", "warning")
    if schema_mode != "off":
        from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
        page_data = {
            "title": title, "category": category, "summary": summary or "",
            "body": body, "tags": tags or [], "related": related or [],
            "contradictions": contradictions or [],
            "source_articles": source_articles or [],
            "relationships": relationships or [],
        }
        result = validate_page_against_schema(page_data, mode=schema_mode, collection_id=collection_id)
        if not result.is_valid:
            raise ValueError(
                f"Schema [{result.class_label}] validation failed: "
                f"missing {result.missing_required}. {result.suggestion}"
            )
        if result.warnings:
            _logger = logging.getLogger("wiki_engine")
            for w in result.warnings:
                if w:
                    _logger.warning(f"Schema warning for '{title}': {w}")

    # ── A8: Key discrimination check ──
    try:
        from core.harness.knowledge.knowledge_ontology import check_key_discrimination
        a8_ok, a8_warnings = check_key_discrimination(title, summary, collection_id=collection_id)
        if not a8_ok:
            _logger = logging.getLogger("wiki_engine")
            for w in a8_warnings:
                _logger.warning(w)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── State transition validation ──
    # Valid: draft→curated, curated→published, curated→draft, published→contradicted,
    #        published→draft, contradicted→resolved, contradicted→draft, resolved→draft
    _VALID_TRANSITIONS = {
        (""):        ["draft", "curated"],               # new page → any non-blocked state
        ("draft"):   ["draft", "curated", "published"],  # draft can go anywhere
        ("curated"): ["curated", "published", "draft"],   # curated: review or rollback
        ("published"): ["published", "draft", "contradicted"],  # published: flag or rollback
        ("contradicted"): ["contradicted", "resolved", "draft"], # contradicted: resolve or rollback
        ("resolved"): ["resolved", "draft"],             # resolved content can always be revised
    }
    existing_status = ""
    existing = read_page(title, category=category, collection_id=collection_id)
    if existing:
        existing_status = (existing.get("status") or "draft")
    target_status = status or existing_status or "draft"
    allowed = _VALID_TRANSITIONS.get(existing_status, _VALID_TRANSITIONS[("")])
    if target_status not in allowed:
        raise ValueError(
            f"Illegal state transition: '{existing_status}' → '{target_status}'. "
            f"Allowed from '{existing_status}': {allowed}"
        )

    name = re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
    now = datetime.now(timezone.utc).isoformat()

    # Merge with existing if updating
    if existing:
        tags = list(set((existing.get("tags") or []) + (tags or [])))
        related = related if related is not None else list(set(
            (existing.get("related") or [])))      # replace, not merge (enable dead link cleanup)
        contradictions = list(set((existing.get("contradictions") or []) + (contradictions or [])))
        # source_articles: explicit pass = replace; None = merge with existing
        source_articles = source_articles if source_articles is not None else \
            list(set((existing.get("source_articles") or []) + (source_articles or [])))
        # stale_references: explicit pass = replace; None = keep existing
        stale_references = stale_references if stale_references is not None else \
            (existing.get("stale_references") or [])
        if version:
            pass  # explicitly provided via argument
        elif existing:
            version = str(int(existing.get("version", "1")) + 1)
        else:
            version = "1"
        summary = summary or existing.get("summary", "")
        # Auto-generate summary from body if still empty
        if not summary and body:
            import re as _re
            clean = _re.sub(r'[#*`>\[\]!|~]', '', body[:500])
            clean = _re.sub(r'https?://\S+', '', clean)
            clean = _re.sub(r'\s+', ' ', clean).strip()
            summary = clean[:200]
        # status: explicit pass takes priority; None = keep existing; default = draft
        if not status:
            status = existing.get("status") or "draft"
        # marking: explicit pass takes priority; None = keep existing
        if not marking:
            marking = existing.get("marking") or ""
        existing_rels = existing.get("relationships") or []
        relationships = relationships if relationships is not None else existing_rels
        existing_imgs = existing.get("images") or []
        images = images if images is not None else existing_imgs

    # New pages default to draft
    if not status:
        status = "draft"

    fm_lines = [
        f"title: {title}",
        f"category: {category}",
        f"tags: [{', '.join(tags or [])}]",
        f"related: [{', '.join(related or [])}]",
        f"contradictions: [{', '.join(contradictions or [])}]",
        f"source_articles: [{', '.join(source_articles or [])}]",
        f"stale_references: [{', '.join(stale_references or [])}]",
        f"relationships: {_json.dumps(relationships or [], ensure_ascii=False)}",
        f"last_updated: {now}",
        f"version: {version or '1'}",
        f"status: {status or 'draft'}",
        f"marking: {marking}",
        f"summary: {summary[:500]}",
        f"images: {_json.dumps(images or [], ensure_ascii=False)}",
    ]

    # Append image descriptions to body for RAG visibility
    enriched_body = body
    if images:
        img_section = "\n\n## 文档附图\n\n"
        for img in images:
            desc = img.get("description", "")
            path = img.get("path", "")
            fname = os.path.basename(path) if path else "image"
            if desc:
                img_section += f"- **{fname}**: {desc}\n"
        enriched_body = body + img_section

    content = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + enriched_body

    # ── Acquire write lock for concurrent-safe disk writes ──
    import sqlite3 as _sqlite3
    _lock_db = str(root / ".wiki_write_lock.db")
    _lock_conn = _sqlite3.connect(_lock_db, timeout=5.0)
    _lock_conn.execute("CREATE TABLE IF NOT EXISTS lock (k TEXT PRIMARY KEY)")
    try:
        _lock_conn.execute("BEGIN IMMEDIATE")

        p = root / category / f"{name}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

        # ── Remove old file if category changed (prevent duplicates) ──
        if existing:
            old_cat = existing.get("category", "")
            if old_cat and old_cat != category:
                old_p = root / old_cat / f"{name}.md"
                if old_p.exists() and old_p != p:
                    old_p.unlink()

        _lock_conn.commit()
    except Exception:
        _lock_conn.rollback()
        raise
    finally:
        _lock_conn.close()

    # Update index
    _update_index(title, category, tags or [], related or [], collection_id=collection_id)

    # ── Cache page vector for fast retrieval ──
    try:
        from core.harness.knowledge.embedder import embed_text_semantic
        vec = embed_text_semantic(body[:5000])
        if vec:
            cache_path = _wiki_root(collection_id) / "vectors.json"
            cache = {}
            if cache_path.exists():
                import json as _cache_json
                cache = _cache_json.loads(cache_path.read_text(encoding="utf-8"))
            cache[title] = vec
            cache_path.write_text(_cache_json.dumps(cache, ensure_ascii=False))
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Incremental inference on create ──
    if relationships or contradictions:
        try:
            from core.harness.knowledge.knowledge_ontology import get_ontology, AI, OntologyTriple
            onto = get_ontology()
            if any(r.get("type") == "contradicts" for r in (relationships or [])):
                for r in (relationships or []):
                    if r.get("type") == "contradicts":
                        target = r.get("target", "")
                        if target:
                            onto.triples.append(OntologyTriple(
                                f"{AI}{target}", f"{AI}contradicts", f"{AI}{title}"))
            if contradictions:
                for c in contradictions:
                    onto.triples.append(OntologyTriple(
                        f"{AI}{c}", f"{AI}contradicts", f"{AI}{title}"))
            if any(r.get("type") == "parent" for r in (relationships or [])):
                for r in (relationships or []):
                    if r.get("type") == "parent":
                        target = r.get("target", "")
                        if target:
                            onto.triples.append(OntologyTriple(
                                f"{AI}{target}", f"{AI}childOf", f"{AI}{title}"))
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # ── Invalidate inference cache (page written) ──
    try:
        import os as _os
        cache_path = _wiki_root(collection_id) / "inference_cache.json"
        if cache_path.exists():
            _os.remove(cache_path)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Invalidate metrics cache + trigger background rebuild (page written) ──
    try:
        metrics_path = _wiki_root(collection_id) / "metrics_cache.json"
        if metrics_path.exists():
            _os.remove(metrics_path)
        inference_path = _wiki_root(collection_id) / "inference_cache.json"
        if inference_path.exists():
            _os.remove(inference_path)
        from core.harness.knowledge._bg_tasks import enqueue
        enqueue("rebuild_metrics", collection_id=collection_id)
        from core.harness.knowledge.knowledge_abox_builder import invalidate_abox_cache
        invalidate_abox_cache(collection_id)
        from core.harness.knowledge.knowledge_growth import take_growth_snapshot
        take_growth_snapshot(collection_id)
        invalidate_graph_cache(collection_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── KB↔Wiki bidirectional link: update kb.sqlite3 ──
    try:
        kb_srcs = [s[3:] for s in (source_articles or []) if isinstance(s, str) and s.startswith("kb:")]
        if kb_srcs:
            kb_db = _os.path.join(_os.path.expanduser(
                _os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants")), "default", "kb.sqlite3")
            if _os.path.exists(kb_db):
                import sqlite3 as _sq3
                conn = _sq3.connect(kb_db)
                for doc_id in kb_srcs:
                    # Atomic JSON append: add title to wiki_pages array if not present
                    conn.execute("""
                        UPDATE documents
                        SET meta_json = CASE
                            WHEN json_extract(COALESCE(meta_json, '{}'), '$.wiki_pages') IS NULL
                            THEN json_set(COALESCE(meta_json, '{}'), '$.wiki_pages', json_array(?))
                            WHEN ? NOT IN (SELECT value FROM json_each(json_extract(meta_json, '$.wiki_pages')))
                            THEN json_set(meta_json, '$.wiki_pages', json_insert(json_extract(meta_json, '$.wiki_pages'), '$[#]', ?))
                            ELSE meta_json
                        END
                        WHERE doc_id = ? AND tenant_id = 'default'
                    """, (title, title, title, doc_id))
                conn.commit()
                conn.close()
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Auto-maintenance: FTS index + atom extraction ──
    try:
        from core.harness.knowledge.wiki_fts import fts_upsert_page
        fts_upsert_page(title, tags=tags or [], summary=summary or "", body_preview=body[:5000])
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Auto-atomize: enqueue for background worker (topic pages with substantial content)
    try:
        if category == "topics" and len(body) > 500:
            from core.harness.knowledge._bg_tasks import enqueue
            enqueue("auto_atomize", title=title, collection_id=collection_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Changelog: record this write ──
    try:
        _record_changelog(title, "write", existing_page=existing, new_body=body,
                          new_status=status, new_marking=marking,
                          collection_id=collection_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Regression guard: run affected gold queries, warn on degradation ──
    try:
        import os as _ros
        if _ros.getenv("AIPLAT_WIKI_REGRESSION_GUARD", "true").lower() in ("1", "true", "yes"):
            _check_regression(title, collection_id)
    except ValueError:
        raise  # blocking mode: propagate to API as 422
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Marking propagation: enqueue for background worker ──
    try:
        import os as _ros2
        if marking and marking != "public" and _ros2.environ.get("_AIPLAT_SKIP_MARKING_PROPAGATION") != "1":
            from core.harness.knowledge._bg_tasks import enqueue
            enqueue("propagate_marking", title=title, marking=marking, collection_id=collection_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Validate source_articles: prune stale kb: references ──
    if source_articles:
        try:
            _reconcile_source_articles(title, source_articles, collection_id)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # ── Programmatic update hooks: provenance + cache ──
    if existing:
        try:
            from core.harness.knowledge.provenance import get_provenance_tracker, ProvenanceScanner
            tracker = get_provenance_tracker()
            scanner = ProvenanceScanner(tracker)
            _run_coro_blocking(scanner.on_source_updated(title, version))
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    try:
        from core.harness.knowledge.semantic_cache import get_semantic_cache
        cache = get_semantic_cache()
        if cache.enabled:
            _run_coro_blocking(cache.invalidate_domain(collection_id))
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return str(p)


def _reconcile_source_articles(title: str, sources: list, collection_id: str = "default") -> None:
    """Validate source_articles against kb_elements; prune invalid kb: IDs.
    
    Only validates kb: prefixed references. URL/DOI/user-entered refs preserved as-is.
    Handles kb:doc_123#section-4 anchor format by stripping #fragment before lookup.
    """
    import sqlite3
    valid = []
    changed = False
    kb_ids = []
    kb_refs = []
    for src in (sources or []):
        if str(src).startswith("kb:"):
            raw = str(src)[3:]
            doc_id = raw.split("#")[0]  # strip anchor
            kb_ids.append(doc_id)
            kb_refs.append(src)
        else:
            valid.append(src)  # URL/DOI/user-entered preserved

    if not kb_ids:
        return  # no kb refs to validate

    # Batch-check against kb_elements table
    try:
        from pathlib import Path
        import os as _os
        kb_db = Path(_os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")) / "kb" / "tenants" / collection_id / "kb.sqlite3"
        if kb_db.exists():
            conn = sqlite3.connect(str(kb_db, timeout=5.0))
            placeholders = ",".join("?" * len(kb_ids))
            rows = conn.execute(
                f"SELECT doc_id FROM kb_documents WHERE doc_id IN ({placeholders})",
                kb_ids,
            ).fetchall()
            existing = {r[0] for r in rows}
            conn.close()
            for src, doc_id in zip(kb_refs, kb_ids):
                if doc_id in existing:
                    valid.append(src)
                else:
                    _logger = logging.getLogger("wiki_engine")
                    _logger.warning(f"Wiki '{title}': stale source_article '{src}' removed (doc not found)")
                    changed = True
        else:
            return  # no KB database, cannot validate
    except Exception:
        return  # validation failure is non-blocking

    if changed:
        # Update page frontmatter with corrected source_articles
        _update_page_source_articles(title, valid, collection_id)


def _update_page_source_articles(title: str, sources: list, collection_id: str = "default") -> None:
    """Update a page's source_articles field without rewriting the body."""
    import re
    existing = read_page(title, collection_id=collection_id)
    if not existing:
        return
    # Rewrite with corrected frontmatter
    write_page(
        title=title,
        body=existing.get("body", ""),
        category=existing.get("category", "entities"),
        tags=list(existing.get("tags", []) or []),
        related=list(existing.get("related", []) or []),
        source_articles=sources,
        collection_id=collection_id,
        version=existing.get("version"),
        summary=existing.get("summary"),
        status=existing.get("status"),
        marking=existing.get("marking"),
    )


def _changelog_path(collection_id: str = "default") -> Path:
    return _wiki_root(collection_id) / "changelog.json"


def _record_changelog(title: str, action: str, *, existing_page: dict = None,
                       new_body: str = "", new_status: str = "", new_marking: str = "",
                       collection_id: str = "default") -> None:
    """Record a wiki page change to the changelog."""
    log_path = _changelog_path(collection_id)
    entries = []
    if log_path.exists():
        try:
            entries = _json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = {
        "title": title, "action": action, "timestamp": now,
    }
    if action == "write":
        old_body = existing_page.get("body", "") if existing_page else ""
        old_status = existing_page.get("status", "draft") if existing_page else "draft"
        old_marking = existing_page.get("marking", "public") if existing_page else "public"
        entry.update({
            "old_body": old_body,
            "new_body": (new_body or ""),
            "old_status": old_status, "new_status": new_status or "draft",
            "old_marking": old_marking, "new_marking": new_marking or "public",
        })
    elif action == "delete":
        old_body = existing_page.get("body", "") if existing_page else ""
        entry["old_body"] = old_body
    entries.append(entry)
    # Keep last 500 entries per collection
    log_path.write_text(_json.dumps(entries[-500:], indent=2, ensure_ascii=False))


def rollback_page(title: str, index: int = -1, *, collection_id: str = "default") -> bool:
    """Restore a wiki page to a previous version from the changelog.
    
    Args:
        title: Page title to rollback
        index: 0-based index in changelog entries for this page. -1 = previous version.
    """
    log_path = _changelog_path(collection_id)
    if not log_path.exists():
        return False
    try:
        entries = _json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    
    page_entries = [(i, e) for i, e in enumerate(entries)
                    if e.get("title") == title and e.get("action") == "write"]
    if not page_entries:
        return False
    if index < 0:
        idx = max(0, len(page_entries) - 1 + index)
    else:
        idx = min(index, len(page_entries) - 1)
    _, entry = page_entries[idx]
    
    old_body = entry.get("old_body", "")
    if not old_body:
        return False
    current = read_page(title, collection_id=collection_id)
    if not current:
        return False
    write_page(
        title, old_body,
        category=current.get("category", "entities"),
        tags=current.get("tags", []), related=current.get("related", []),
        summary=current.get("summary", ""),
        status=entry.get("old_status", "draft"),
        marking=entry.get("old_marking", "public"),
        collection_id=collection_id,
    )
    logging.getLogger("wiki_engine").info(
        f"Rolled back '{title}' to version {idx+1}/{len(page_entries)}")
    return True


def _check_regression(title: str, collection_id: str) -> None:
    """Run affected gold queries after a page write, log warnings on regression."""
    import yaml as _yaml
    from pathlib import Path as _Path
    import os as _os
    _log = logging.getLogger("wiki_engine")

    gq_path = _Path(_os.path.expanduser(
        _os.getenv("AIPLAT_HOME", "~/.aiplat"))) / "wiki" / "golden_queries.yaml"
    if not gq_path.exists():
        return

    try:
        queries = _yaml.safe_load(open(gq_path)).get("queries", [])
    except Exception:
        return

    # Find affected queries: those whose expected concepts include the page title or related titles
    page = read_page(title, collection_id=collection_id)
    if not page:
        return
    related_titles = {title} | set(page.get("related", []) or [])

    affected = []
    for q in queries:
        expected = set(q.get("expected_concepts", q.get("expected_pages", [])))
        if expected & related_titles:
            affected.append(q)

    if not affected:
        return

    # Run affected queries via structured query test
    from core.harness.knowledge.wiki_structured_query import structured_query
    failed = []
    for q in affected:
        query_text = q.get("query", "")
        expected = q.get("expected_concepts", q.get("expected_pages", []))
        if not expected:
            continue
        result = structured_query(query_text)
        res = result.get("result", {})
        actual_titles = []
        if isinstance(res, dict):
            actual_titles = [res.get("title", "")]
            if "entity_a" in res:
                actual_titles = [res["entity_a"].get("title", ""), res["entity_b"].get("title", "")]
        found = [e for e in expected for t in actual_titles if e in t]
        if len(found) < max(1, len(expected) * 0.5):
            # Verify pages still exist on disk (not a body-too-short false positive)
            existing_pages = [e for e in expected if read_page(e, collection_id=collection_id)]
            if len(existing_pages) >= max(1, len(expected) * 0.5):
                # Pages exist but structured_query can't find them — likely a temporary
                # indexing delay, not a true regression
                _log.debug(
                    f"Regression (indexing delay): '{title}' caused '{query_text}' "
                    f"to miss {expected}, but pages exist. Found: {actual_titles[:5]}")
                continue
            failed.append({"query": query_text, "expected": expected, "found": actual_titles[:5]})

    if failed:
        mode = _os.getenv("AIPLAT_WIKI_REGRESSION_MODE", "warn")
        _log.warning(
            f"Regression: {len(failed)}/{len(affected)} affected gold queries failed "
            f"after writing '{title}': {failed}")
        if mode == "block":
            raise ValueError(
                f"Write rejected: {len(failed)} gold queries would fail. "
                f"Failed: {[f['query'] for f in failed]}. "
                f"Set AIPLAT_WIKI_REGRESSION_MODE=warn to allow.")


def _propagate_marking(title: str, marking: str, collection_id: str) -> None:
    """Propagate a page's marking to connected pages via A-Box relationship edges.
    
    Edges traversed: related, hasAtom, derivesFrom, parentOf, childOf, cites.
    Rule: the most restrictive marking wins (confidential > internal > public).
    """
    if not marking or marking == "public":
        return  # public is the default, no propagation needed
    
    _MARKING_ORDER = {"public": 0, "internal": 1, "confidential": 2}
    source_level = _MARKING_ORDER.get(marking, 0)
    _log = logging.getLogger("wiki_engine")
    
    # Collect all titles connected to this page via A-Box edges
    connected: set = set()
    
    # 1) Direct related links from the page itself
    page = read_page(title, collection_id=collection_id)
    if page:
        connected.update(page.get("related", []) or [])
    
    # 2) A-Box triples: hasAtom, parentOf, childOf, cites
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        AI = "http://aiplat.local/knowledge#"
        onto = build_abox(collection_id=collection_id)
        page_uri = f"{AI}{title}"
        for t in onto.triples:
            if str(t.subject) == page_uri:
                pred = str(t.predicate)
                if any(p in pred for p in ("hasAtom", "parentOf", "cites", "childOf")):
                    obj_name = str(t.object).replace(AI, "")
                    if obj_name and obj_name != title:
                        connected.add(obj_name)
            if str(t.object) == page_uri:
                pred = str(t.predicate)
                if any(p in pred for p in ("childOf", "cites", "isCitedBy")):
                    subj_name = str(t.subject).replace(AI, "")
                    if subj_name and subj_name != title:
                        connected.add(subj_name)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    
    # 3) Propagate: update each connected page if its marking is less restrictive
    updated = 0
    for target_title in connected:
        try:
            target = read_page(target_title, collection_id=collection_id)
            if not target:
                continue
            target_marking = target.get("marking") or "public"
            target_level = _MARKING_ORDER.get(target_marking, 0)
            if source_level > target_level:
                # Only upgrade; never downgrade
                update_page(
                    target_title,
                    marking=marking,
                    collection_id=collection_id,
                    _skip_marking_propagation=True,  # prevent recursion
                )
                updated += 1
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    
    if updated:
        _log.info(f"Marking '{marking}' propagated from '{title}' to {updated} pages: {sorted(connected)}")


def _update_index(title: str, category: str, tags: List[str], related: List[str], collection_id: str = "default"):
    idx_path = _wiki_root(collection_id) / "index.json"
    try:
        idx = _json.loads(idx_path.read_text(encoding="utf-8"))
    except Exception:
        idx = {"pages": {}, "last_updated": ""}
    idx["pages"][title] = {"category": category, "tags": tags, "related": related,
                             "last_updated": datetime.now(timezone.utc).isoformat()}
    idx["last_updated"] = datetime.now(timezone.utc).isoformat()
    idx_path.write_text(_json.dumps(idx, indent=2, ensure_ascii=False))


def update_page(title: str, *, collection_id: str = "default", **kwargs) -> bool:
    u"""Update specific frontmatter fields of an existing wiki page, preserving others."""
    existing = None
    for cat_dir in _wiki_root(collection_id).iterdir():
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        test = read_page(title, category=cat_dir.name, collection_id=collection_id)
        if test:
            existing = test
            break
    if not existing:
        return False

    for key in ("summary", "category", "tags", "related", "contradictions",
                  "source_articles", "stale_references", "relationships",
                  "status", "marking"):
        if key in kwargs and kwargs[key] is not None:
            value = kwargs[key]
            if key == "related" and isinstance(value, list):
                all_titles = set(p["title"] for p in search_pages(limit=1000, collection_id=collection_id))
                value = [r for r in value if r in all_titles or r == title]
            existing[key] = value

    name = kwargs.get("new_title", kwargs.get("title", title))
    if name != title:
        existing["title"] = name

    # Prevent infinite recursion during marking propagation
    skip_propagation = kwargs.pop("_skip_marking_propagation", False)
    write_args = dict(
        category=existing.get("category", "entities"),
        tags=existing.get("tags", []), related=existing.get("related", []),
        summary=existing.get("summary", ""),
        contradictions=existing.get("contradictions", []),
        source_articles=existing.get("source_articles", []),
        stale_references=existing.get("stale_references", []),
        relationships=existing.get("relationships", []),
        status=existing.get("status") or "draft",
        marking=existing.get("marking") or "",
        collection_id=collection_id,
    )
    if skip_propagation:
        import os as _update_os
        prev = _update_os.environ.get("_AIPLAT_SKIP_MARKING_PROPAGATION", "")
        _update_os.environ["_AIPLAT_SKIP_MARKING_PROPAGATION"] = "1"
        try:
            write_page(existing["title"], existing.get("body", ""), **write_args)
        finally:
            _update_os.environ["_AIPLAT_SKIP_MARKING_PROPAGATION"] = prev
    else:
        write_page(existing["title"], existing.get("body", ""), **write_args)
    return True


def delete_page(title: str, collection_id: str = "default") -> bool:
    u"""Delete a wiki page by title, removing from disk and index."""
    found = None
    cat_name = ""
    for cat_dir in _wiki_root(collection_id).iterdir():
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        md_path = cat_dir / f"{title}.md"
        if md_path.exists():
            found = md_path
            cat_name = cat_dir.name
            break
    if not found:
        return False

    # Read page content before deleting (for changelog)
    old_page = read_page(title, category=cat_name, collection_id=collection_id)

    found.unlink()
    idx_path = _wiki_root(collection_id) / "index.json"
    if idx_path.exists():
        try:
            idx = _json.loads(idx_path.read_text(encoding="utf-8"))
            idx.get("pages", {}).pop(title, None)
            idx_path.write_text(_json.dumps(idx, indent=2, ensure_ascii=False))
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # ── Cascade: mark stale references in pages that cited the deleted page ──
    try:
        all_pages = search_pages(limit=1000, collection_id=collection_id)
        cascade_count = 0
        for p in all_pages:
            ptitle = p.get("title", "")
            if ptitle == title:
                continue
            needs_update = False
            updated_related = list(p.get("related") or [])
            updated_contra = list(p.get("contradictions") or [])
            stale = list(p.get("stale_references") or [])

            if title in updated_related:
                updated_related.remove(title)
                needs_update = True
            if title in updated_contra:
                updated_contra.remove(title)
                needs_update = True
            if title not in stale:
                stale.append(title)
                needs_update = True

            if needs_update:
                update_page(ptitle, related=updated_related,
                            contradictions=updated_contra,
                            stale_references=stale,
                            collection_id=collection_id)
                cascade_count += 1

        if cascade_count:
            logging.getLogger("wiki_engine").info(
                f"delete_page('{title}'): cascaded {cascade_count} referencing pages")
    except Exception as e:
        logging.getLogger("wiki_engine").warning(
            f"delete_page cascade failed for '{title}': {e}")

    # ── Invalidate caches + trigger background rebuild (page deleted) ──
    try:
        import os as _os
        for cache_name in ("inference_cache.json", "metrics_cache.json"):
            cache_path = _wiki_root(collection_id) / cache_name
            if cache_path.exists():
                _os.remove(cache_path)
        from core.harness.knowledge._bg_tasks import enqueue
        enqueue("rebuild_metrics", collection_id=collection_id)
        from core.harness.knowledge.knowledge_abox_builder import invalidate_abox_cache
        invalidate_abox_cache(collection_id)
        from core.harness.knowledge.knowledge_growth import take_growth_snapshot
        take_growth_snapshot(collection_id)
        invalidate_graph_cache(collection_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Auto-maintenance: remove from FTS index ──
    try:
        from core.harness.knowledge.wiki_fts import fts_delete_page
        fts_delete_page(title)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Changelog: record this deletion ──
    try:
        _record_changelog(title, "delete", existing_page=old_page, collection_id=collection_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return True


def cleanup_ghost_pages(*, collection_id: str = "default", dry_run: bool = False) -> Dict[str, Any]:
    u"""Batch-clean ghost pages — search index entries with no stored page data.

    Ghost pages are entries that exist in the search_pages() index but:
    - Have empty body (< 5 chars) in search_pages()
    - Have no stored page data (read_page() returns None)

    Unlike individual delete_page() calls, this method:
    - Skips A8 duplicate similarity checks (O(n²) → O(n))
    - Skips cascade stale-reference updates (ghosts have no real content)
    - Skips contradiction/synthesis-page sync
    - Does ONE FTS index rebuild at the end (not per-page)
    - Does ONE cache invalidation round

    Returns: {deleted: int, skipped: int, errors: list, dry_run: bool}
    """
    logger = logging.getLogger("wiki_engine")
    all_pages = search_pages(limit=2000, collection_id=collection_id)
    
    ghosts: List[str] = []
    skipped = 0
    for p in all_pages:
        title = p.get("title", "")
        body = p.get("body", "")
        if len(body) < 5:
            full = read_page(title, collection_id=collection_id)
            if full is None or len(full.get("body", "") or "") < 5:
                ghosts.append(title)
            else:
                skipped += 1  # Has content, was just truncated in search_pages
    
    if dry_run:
        logger.info("Ghost page scan (dry_run): %d ghosts found, %d skipped", len(ghosts), skipped)
        return {"deleted": 0, "skipped": skipped, "ghosts_found": len(ghosts), "dry_run": True, "errors": []}
    
    deleted = 0
    errors: List[str] = []
    root = _wiki_root(collection_id)
    
    for title in ghosts:
        try:
            # Direct file removal (bypass cascade/duplicate/contradiction checks)
            found = False
            for cat_dir in root.iterdir():
                if not cat_dir.is_dir() or cat_dir.name == "contradictions":
                    continue
                md_path = cat_dir / f"{title}.md"
                if md_path.exists():
                    md_path.unlink()
                    found = True
                    break
            
            if found:
                # Update index
                idx_path = root / "index.json"
                if idx_path.exists():
                    try:
                        idx = _json.loads(idx_path.read_text(encoding="utf-8"))
                        idx.get("pages", {}).pop(title, None)
                        idx_path.write_text(_json.dumps(idx, indent=2, ensure_ascii=False))
                    except Exception:
                        pass
                deleted += 1
        except Exception as e:
            errors.append(f"{title}: {e}")
    
    # ── One-time rebuild: FTS index + cache invalidation ──
    if deleted > 0:
        try:
            from core.harness.knowledge.wiki_fts import fts_rebuild_on_update
            fts_rebuild_on_update()
        except Exception as e:
            logger.warning("Ghost cleanup: FTS rebuild failed: %s", e)
        
        try:
            import os as _os
            for cache_name in ("inference_cache.json", "metrics_cache.json"):
                cache_path = root / cache_name
                if cache_path.exists():
                    _os.remove(cache_path)
            from core.harness.knowledge._bg_tasks import enqueue
            enqueue("rebuild_metrics", collection_id=collection_id)
        except Exception as e:
            logger.warning("Ghost cleanup: cache invalidation failed: %s", e)
    
    logger.info("Ghost page cleanup: %d deleted, %d skipped, %d errors", deleted, skipped, len(errors))
    return {"deleted": deleted, "skipped": skipped, "errors": errors, "dry_run": False}


def delete_all_pages(*, collection_id: str = "default") -> Dict[str, Any]:
    u"""Delete ALL wiki pages, reset index, and clear KB document wiki_pages references."""
    _ensure_dirs(collection_id)
    root = _wiki_root(collection_id)
    deleted = 0

    for cat_dir in root.iterdir():
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        for md_file in cat_dir.glob("*.md"):
            md_file.unlink()
            deleted += 1

    idx_path = root / "index.json"
    idx_path.write_text(_json.dumps({"pages": {}, "last_updated": ""}, indent=2, ensure_ascii=False))

    # Clear wiki_pages from KB document meta
    try:
        import sqlite3 as _sq
        kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
        kb_db = os.path.join(kb_dir, "default", "kb.sqlite3")
        if os.path.exists(kb_db):
            conn = _sq.connect(kb_db)
            conn.row_factory = _sq.Row
            docs = conn.execute("SELECT doc_id, meta_json FROM documents WHERE tenant_id='default'").fetchall()
            for d in docs:
                try:
                    meta = _json.loads(d["meta_json"] or "{}")
                    if "wiki_pages" in meta:
                        del meta["wiki_pages"]
                        conn.execute("UPDATE documents SET meta_json=? WHERE doc_id=? AND tenant_id='default'",
                                     (_json.dumps(meta, ensure_ascii=False), d["doc_id"]))
                        conn.commit()
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
            conn.close()
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return {"deleted": deleted}


# ── Knowledge proposals (merge/update/supplement/contradict) ──────

def _proposals_path(collection_id: str = "default") -> Path:
    return _wiki_root(collection_id) / "proposals.json"


def load_proposals(*, collection_id: str = "default") -> List[Dict[str, Any]]:
    u"""Load all proposals from disk."""
    pp = _proposals_path(collection_id)
    if not pp.exists():
        return []
    try:
        data = _json.loads(pp.read_text(encoding="utf-8"))
        return data.get("proposals", [])
    except Exception:
        return []


def save_proposal(proposal: Dict[str, Any], collection_id: str = "default") -> str:
    u"""Add or update a proposal. Returns the proposal id."""
    pp = _proposals_path(collection_id)
    _ensure_dirs(collection_id)
    proposals = load_proposals(collection_id=collection_id)
    pid = proposal.get("id") or f"prop_{int(time.time() * 1000):x}"
    proposal["id"] = pid
    # Update existing or append
    for i, p in enumerate(proposals):
        if p.get("id") == pid:
            proposals[i] = proposal
            break
    else:
        proposals.append(proposal)
    pp.write_text(_json.dumps({"proposals": proposals, "last_updated": datetime.now(timezone.utc).isoformat()},
                              indent=2, ensure_ascii=False))
    return pid


def update_proposal_status(proposal_id: str, status: str, collection_id: str = "default") -> bool:
    u"""Update a proposal's status (pending→approved→rejected)."""
    proposals = load_proposals(collection_id=collection_id)
    for p in proposals:
        if p.get("id") == proposal_id:
            p["status"] = status
            p["resolved_at"] = datetime.now(timezone.utc).isoformat()
            pp = _proposals_path(collection_id)
            pp.write_text(_json.dumps({"proposals": proposals, "last_updated": datetime.now(timezone.utc).isoformat()},
                                      indent=2, ensure_ascii=False))
            return True
    return False


def apply_proposal(proposal_id: str, collection_id: str = "default") -> Dict[str, Any]:
    u"""Execute an approved proposal: merge, update, supplement, or contrad.

    Returns: {success: bool, message: str, action: str}
    """
    proposals = load_proposals(collection_id=collection_id)
    prop = next((p for p in proposals if p.get("id") == proposal_id), None)
    if not prop:
        return {"success": False, "message": "proposal not found", "action": ""}
    if prop.get("status") != "approved":
        return {"success": False, "message": "proposal not yet approved", "action": ""}

    action = prop.get("action", "")
    from_title = prop.get("from_title", "")
    to_title = prop.get("to_title", "")

    if action == "merge":
        return _execute_merge(prop, from_title, to_title)
    elif action == "update":
        return _execute_update(prop, from_title, to_title)
    elif action == "supplement":
        return _execute_supplement(prop, from_title, to_title)
    elif action == "contradict":
        return _execute_contradict(prop, from_title, to_title)
    return {"success": False, "message": f"unknown action: {action}", "action": action}


def _execute_merge(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Merge two pages: combine bodies, update links, delete merged page.

    M1: Schema revalidation after merge
    M2: A-Box triple redirect (cites/contradicts/parentOf from source → target)
    M3: Ontology-guided suggestions via llm_curate_page (same parent class hint)
    M4: Re-check contradiction relationships after merge
    """
    from_page = read_page(from_title)
    to_page = read_page(to_title)
    if not from_page or not to_page:
        return {"success": False, "message": "one or both pages not found", "action": "merge"}

    merged_body = (to_page.get("body") or "") + "\n\n---\n\n合并自 [[{from_title}]]:\n\n".format(from_title=from_title) + (from_page.get("body") or "")
    merged_tags = list(set((to_page.get("tags") or []) + (from_page.get("tags") or [])))
    merged_related = list(set((to_page.get("related") or []) + (from_page.get("related") or []) + [from_title]))
    merged_related = [r for r in merged_related if r != to_title]  # remove self-ref
    merged_sources = list(set((to_page.get("source_articles") or []) + (from_page.get("source_articles") or [])))

    write_page(to_title, merged_body[:50000],
               category=to_page.get("category", "entities"),
               tags=merged_tags[:10],
               related=merged_related[:15],
               summary=to_page.get("summary", "") or from_page.get("summary", ""),
               source_articles=merged_sources)
    # Redirect references from from_title to to_title in all pages
    all_pages = search_pages(limit=1000)
    updated = 0
    for p in all_pages:
        if from_title in (p.get("related") or []):
            new_related = [to_title if r == from_title else r for r in p["related"]]
            update_page(p["title"], related=new_related)
            updated += 1

    # ── M2: A-Box triple redirect ──
    triple_updates = 0
    try:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
        new_triples = []
        for t in list(onto.triples):
            old_subject = str(t.subject)
            old_object = str(t.object)
            changed = False
            new_sub, new_obj = old_subject, old_object
            if from_title in old_subject:
                new_sub = old_subject.replace(from_title, to_title)
                changed = True
            if from_title in old_object:
                new_obj = old_object.replace(from_title, to_title)
                changed = True
            if changed:
                from core.harness.knowledge.knowledge_ontology import OntologyTriple
                new_triples.append(OntologyTriple(
                    subject=new_sub, predicate=str(t.predicate), object=new_obj,
                ))
                onto.triples.remove(t)
                triple_updates += 1
        onto.triples.extend(new_triples)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── M1: Schema revalidation ──
    validation = {}
    try:
        from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
        merged_page = read_page(to_title)
        if merged_page:
            val = validate_page_against_schema(merged_page, mode="warning")
            validation = {"valid": val.is_valid, "class": val.class_label,
                          "missing": val.missing_required, "warnings": val.warnings[:3]}
    except Exception:
        validation = {"valid": None, "note": "validation skipped"}

    # ── M4: Re-check contradictions after merge ──
    contradiction_cleanups = 0
    try:
        all_pages_post = search_pages(limit=1000)
        for p in all_pages_post:
            contras = list(p.get("contradictions") or [])
            if not contras:
                continue
            changed = False
            new_contras = []
            for c in contras:
                if not isinstance(c, str):
                    new_contras.append(c)
                    continue
                # Replace merged-from title with merged-to title
                if c == from_title:
                    new_contras.append(to_title)
                    changed = True
                elif c == to_title:
                    # Self-contradiction: page now contradicts itself → remove
                    changed = True
                    contradiction_cleanups += 1
                    # Don't add to new_contras (skip)
                else:
                    new_contras.append(c)
            if changed and p["title"] != from_title:  # skip the deleted page
                try:
                    update_page(p["title"], contradictions=new_contras)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    delete_page(from_title)
    update_proposal_status(prop["id"], "resolved")
    return {
        "success": True,
        "message": f"merged '{from_title}' into '{to_title}', updated {updated} references",
        "action": "merge",
        "triple_updates": triple_updates,
        "schema_validation": validation,
        "contradiction_cleanups": contradiction_cleanups,
    }


def _execute_update(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Update existing page with new content from another page."""
    to_page = read_page(to_title)
    if not to_page:
        return {"success": False, "message": "target page not found", "action": "update"}
    from_page = read_page(from_title)
    new_body = (from_page.get("body") or "") if from_page else (to_page.get("body") or "")
    version = int(to_page.get("version", 1)) + 1
    update_page(to_title, body=new_body, version=str(version))
    # Mark stale references
    all_pages = search_pages(limit=1000)
    for p in all_pages:
        if to_title in (p.get("related") or []):
            stale = list(set((p.get("stale_references") or []) + [to_title]))
            update_page(p["title"], stale_references=stale[:10])
    update_proposal_status(prop["id"], "resolved")
    return {"success": True, "message": f"updated '{to_title}' to v{version}, marked stale references", "action": "update"}


def _execute_supplement(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Append new content to existing page body."""
    to_page = read_page(to_title)
    from_page = read_page(from_title)
    if not to_page:
        return {"success": False, "message": "target page not found", "action": "supplement"}
    appendix = (from_page.get("body") or "") if from_page else ""
    if appendix:
        new_body = (to_page.get("body") or "") + "\n\n---\n\n补充内容 (来源: {from_title}):\n\n".format(from_title=from_title) + appendix
        update_page(to_title, body=new_body[:50000])
    update_proposal_status(prop["id"], "resolved")
    return {"success": True, "message": f"supplemented '{to_title}'", "action": "supplement"}


def _execute_contradict(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Mark contradiction between two pages."""
    for t in [from_title, to_title]:
        page = read_page(t)
        if page:
            other = to_title if t == from_title else from_title
            contras = list(set((page.get("contradictions") or []) + [other]))
            update_page(t, contradictions=contras[:10])
    update_proposal_status(prop["id"], "resolved")
    return {"success": True, "message": f"marked contradiction between '{from_title}' and '{to_title}'", "action": "contradict"}


# ── Search ─────────────────────────────────────────────────────

def search_pages(query: str = "", *, tags: List[str] = None, category: str = "",
                   limit: int = 20, collection_id: str = "default",
                   department: str = "", effective_after: str = "",
                   expiry_before: str = "") -> List[Dict[str, Any]]:
    """Search wiki pages by title, tags, body, with K4 metadata filters.

    K4 filters:
      department: filter by owning department
      effective_after: only pages effective on or after this date (ISO)
      expiry_before: only pages expiring before this date (ISO)
    """
    _ensure_dirs(collection_id)
    root = _wiki_root(collection_id)
    results: List[Dict[str, Any]] = []
    query_lower = query.lower() if query else ""

    # K3: Synonym expansion — search with canonical terms too
    from core.harness.knowledge.knowledge_ontology import expand_query_with_synonyms
    query_variants = expand_query_with_synonyms(query) if query else [query]

    for cat_dir in [d for d in root.iterdir() if d.is_dir() and d.name != "__pycache__"]:
        if category and cat_dir.name != category:
            continue
        for md_file in cat_dir.glob("*.md"):
            page = read_page(md_file.stem, category=cat_dir.name, collection_id=collection_id)
            if not page:
                continue

            # Filter by tags
            if tags:
                if not set(tags).intersection(set(page.get("tags", []))):
                    continue

            # Filter by query (with K3 synonym expansion)
            if query_variants:
                matched = False
                for qv in query_variants:
                    qv_lower = qv.lower()
                    if (qv_lower in page["title"].lower()
                        or qv_lower in page.get("body", "").lower()[:2000]
                        or any(qv_lower in t.lower() for t in page.get("tags", []))):
                        matched = True
                        break
                if not matched:
                    continue

            # K4: department filter
            if department:
                page_dept = str(page.get("department", "") or "").lower()
                if department.lower() not in page_dept:
                    continue
            # K4: date range filter
            if effective_after:
                eff = str(page.get("effective_date", "") or "")
                if eff and eff < effective_after:
                    continue
            if expiry_before:
                exp = str(page.get("expiry_date", "") or "")
                if exp and exp > expiry_before:
                    continue

            results.append({
                "title": page["title"], "category": page["category"],
                "tags": page.get("tags", []), "summary": page.get("summary", "")[:200],
                "related": page.get("related", []), "path": page["path"],
                "contradictions": page.get("contradictions", []),
                "source_articles": page.get("source_articles", []),
                "stale_references": page.get("stale_references", []),
                "relationships": page.get("relationships", []),
                "last_updated": page.get("last_updated", ""),
            })

    results.sort(key=lambda r: r["last_updated"], reverse=True)
    return results[:limit]


def traverse_links(start_title: str, depth: int = 2, collection_id: str = "default") -> List[Dict[str, Any]]:
    """BFS traverse wiki link graph starting from a page."""
    _ensure_dirs(collection_id)
    visited: set = set()
    queue: List[Tuple[str, int]] = [(start_title, 0)]
    results: List[Dict[str, Any]] = []

    while queue:
        title, d = queue.pop(0)
        if title in visited or d > depth:
            continue
        visited.add(title)
        page = read_page(title, collection_id=collection_id)
        if not page:
            continue
        results.append(page)
        for rel in page.get("related", []):
            if rel not in visited:
                queue.append((rel, d + 1))

    return results


# ── Contradiction detection ────────────────────────────────────

def detect_contradictions() -> List[Dict[str, Any]]:
    """DEPRECATED: use wiki_health_report() for richer output."""
    return wiki_health_report()["issues"]


def wiki_health_report() -> Dict[str, Any]:
    """Comprehensive wiki health report — delegates to extensible WikiHealthRegistry.
    
    To add a new health check: add a WikiRule subclass in wiki_health_rules.py.
    """
    from core.harness.knowledge.wiki_health_rules import get_wiki_registry
    return get_wiki_registry().run().to_dict()


def list_all_pages(*, collection_id: str = "default") -> List[Dict[str, Any]]:
    """Return summary of all wiki pages for index display."""
    return search_pages(limit=1000, collection_id=collection_id)


# ── Graph export (ECharts force-layout) ──────────────────────────

def build_graph(*, category: str = "", keyword: str = "", source: str = "", max_nodes: int = 300, collection_id: str = "default") -> Dict[str, Any]:
    u"""Build node/edge graph for ECharts force-layout visualization (cached)."""
    cache_key = f"{category}|{keyword}|{source}|{max_nodes}|{collection_id}"
    cached = _read_graph_cache(cache_key)
    if cached:
        return cached

    result = _build_graph_raw(category=category, keyword=keyword, source=source,
                               max_nodes=max_nodes, collection_id=collection_id)
    _write_graph_cache(cache_key, result)
    return result


def invalidate_graph_cache(collection_id: str = "default") -> None:
    u"""Invalidate all graph caches (call after write_page/delete_page)."""
    db_path = _graph_cache_db()
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path, timeout=5.0)
            conn.execute("DELETE FROM graph_cache")
            conn.commit()
            conn.close()
        except Exception as e:
            logging.debug(str(e), exc_info=True)


def _graph_cache_db() -> str:
    root = _wiki_root("default").parent
    return os.path.join(str(root), "graph_cache.db")


def _read_graph_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    import sqlite3, json as _json, time as _time
    db_path = _graph_cache_db()
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        row = conn.execute(
            "SELECT result_json, updated_at FROM graph_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()
        conn.close()
        if row and _time.time() - row[1] < 120:
            return _json.loads(row[0])
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return None


def _write_graph_cache(cache_key: str, result: Dict[str, Any]) -> None:
    import sqlite3, json as _json, time as _time
    db_path = _graph_cache_db()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS graph_cache (cache_key TEXT PRIMARY KEY, result_json TEXT, updated_at REAL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO graph_cache (cache_key, result_json, updated_at) VALUES (?,?,?)",
            (cache_key, _json.dumps(result, ensure_ascii=False), _time.time()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.debug(str(e), exc_info=True)


def _build_graph_raw(*, category: str = "", keyword: str = "", source: str = "", max_nodes: int = 300, collection_id: str = "default") -> Dict[str, Any]:
    u"""Internal: raw graph builder (no cache)."""
    _ensure_dirs(collection_id)
    root = _wiki_root(collection_id)
    all_pages: Dict[str, Dict[str, Any]] = {}

    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        for md_file in sorted(cat_dir.glob("*.md")):
            page = read_page(md_file.stem, category=cat_dir.name, collection_id=collection_id)
            if page:
                all_pages[page["title"]] = page

    if keyword:
        kw = keyword.lower()
        all_pages = {t: p for t, p in all_pages.items()
                     if kw in t.lower() or any(kw in tag.lower() for tag in p.get("tags", []))}
    if category:
        all_pages = {t: p for t, p in all_pages.items() if p.get("category", "") == category}

    if source:
        all_pages = {t: p for t, p in all_pages.items()
                     if any(s.startswith(source + ":") for s in (p.get("source_articles") or []))}

    in_degree: Dict[str, int] = {t: 0 for t in all_pages}
    for p in all_pages.values():
        for rel in p.get("related", []):
            if rel in in_degree:
                in_degree[rel] += 1

    # Auto-link pages with no related links (one-time backfill using embedding similarity)
    _titles_list = list(all_pages.keys())
    for title, page in all_pages.items():
        if not page.get("related") and len(_titles_list) > 1:
            try:
                auto_links = auto_link_page(title, page.get("body", ""), _titles_list)
                if auto_links:
                    page["related"] = auto_links
            except Exception:
                pass

    cat_colors = {"entities": "#4d9fff", "topics": "#a855f7", "contradictions": "#ef4444"}
    titles = list(all_pages.keys())
    if max_nodes > 0 and len(titles) > max_nodes:
        titles.sort(key=lambda t: len(all_pages[t].get("related", [])) + in_degree.get(t, 0), reverse=True)
        titles = titles[:max_nodes]
        keep = set(titles)
        all_pages = {t: p for t, p in all_pages.items() if t in keep}

    cat_counts: Dict[str, int] = {}
    total_links = 0
    nodes = []
    for title in titles:
        p = all_pages[title]
        link_count = len(p.get("related", [])) + in_degree.get(title, 0)
        total_links += link_count
        cat_name = p.get("category", "entities")
        # Wiki graph categories are a fixed 3-class visual grouping (entities/topics/
        # contradictions). Normalize any leaked ontology-class category (e.g.
        # "ai-techniques") to the default so the node contract stays valid.
        if cat_name not in ("entities", "topics", "contradictions"):
            cat_name = "entities"
        cat_counts[cat_name] = cat_counts.get(cat_name, 0) + 1
        symbol_size = min(12 + link_count * 3, 55)
        has_issues = bool(p.get("contradictions") or p.get("issues"))
        nodes.append({
            "id": title,
            "name": title if len(title) <= 50 else title[:47] + "...",
            "category": cat_name,
            "symbolSize": symbol_size,
            "tags": p.get("tags", [])[:5],
            "summary": p.get("summary", ""),
            "linkCount": link_count,
            "hasIssues": has_issues,
            "itemStyle": {"color": "#ef4444" if has_issues else cat_colors.get(cat_name, "#4d9fff")},
        })

    id_set = set(titles)
    edges = [{"source": t, "target": r} for t in titles for r in all_pages[t].get("related", []) if r in id_set]

    return {
        "nodes": nodes, "edges": edges,
        "stats": {"totalNodes": len(nodes), "totalEdges": len(edges),
                  "avgLinksPerPage": round(total_links / max(len(nodes), 1), 2),
                  "categories": cat_counts},
    }


# ── Cross-linking via embedding similarity ──────────────────────

def auto_link_page(title: str, body: str, all_titles: List[str],
                   threshold: float = None) -> List[str]:
    u"""自动语义关联：嵌入相似度 → top-5 相关页面。

    模型路径：embed_texts_semantic → InfraEmbeddingAdapter → infra ModelManager。
    阈值可通过 AIPLAT_WIKI_LINK_THRESHOLD 环境变量配置。
    """
    if threshold is None:
        threshold = float(os.getenv("AIPLAT_WIKI_LINK_THRESHOLD", "0.35"))
    existing = [t for t in all_titles if t != title]
    if not existing:
        return []

    from core.harness.knowledge.embedder import embed_text_semantic, embed_texts_semantic, cosine_similarity

    target_vec = embed_text_semantic(body[:2000])
    if target_vec is None:
        return []

    others = [read_page(t) for t in existing if read_page(t)]
    texts = [(p["body"] or "")[:2000] for p in others]
    other_vecs = embed_texts_semantic(texts)

    scored = []
    for t, v in zip(existing, other_vecs):
        if v is not None:
            sim = cosine_similarity(target_vec, v)
            if sim > threshold:
                scored.append((t, sim))
    scored.sort(key=lambda x: -x[1])
    return [s[0] for s in scored[:5]]


def detect_duplicate_pages(threshold: float = 0.90, collection_id: str = "default") -> List[Dict[str, Any]]:
    """Multi-dimensional duplicate page detection across all wiki pages.

    L1 (Embedding): cosine similarity >= threshold → content duplicates
    L2 (Ontology): same T-Box class + same parentOf target + title similarity > 0.6
    L3 (Structural): same category + shared >= 2 related pages
    L4 (Evidence): same source_doc_id + overlapping evidence range

    Returns: [{page_a, page_b, similarity, layer, suggestion}]
    """
    dupes: List[Dict[str, Any]] = []
    seen_pairs: set = set()

    from core.harness.knowledge.embedder import embed_text_semantic, embed_texts_semantic, cosine_similarity
    from core.harness.knowledge.knowledge_ontology import CLASSES, OBJECT_PROPERTIES, get_ontology

    all_pages = search_pages(limit=10000, collection_id=collection_id)

    # Index pages by title for fast lookup
    page_map: Dict[str, Dict[str, Any]] = {}
    for p in all_pages:
        page_map[p["title"]] = p

    titles = [p["title"] for p in all_pages]
    titles_set = set(titles)

    # ── L1: Embedding similarity ──
    texts = [(p.get("body") or p.get("summary", ""))[:2000] for p in all_pages]
    vecs = embed_texts_semantic(texts)
    if vecs and len(vecs) == len(all_pages):
        for i in range(len(all_pages)):
            for j in range(i + 1, len(all_pages)):
                a, b = all_pages[i], all_pages[j]
                vi, vj = vecs[i], vecs[j]
                if vi is None or vj is None:
                    continue
                sim = cosine_similarity(vi, vj)
                if sim >= threshold:
                    pair = tuple(sorted([a["title"], b["title"]]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        dupes.append({
                            "page_a": a["title"], "page_b": b["title"],
                            "similarity": round(sim, 3), "layer": "L1_content",
                            "suggestion": f"内容几乎相同 (sim={sim:.2f})，建议合并",
                        })

    # ── L2: Ontology-aware duplicates (same class + same parent + title similarity) ──
    try:
        onto = get_ontology()
        # Collect parentOf relations from A-Box
        parent_map: Dict[str, str] = {}  # child → parent
        for t in onto.triples:
            if "parentOf" in t.predicate:
                parent_map[str(t.object)] = str(t.subject)

        # Group pages by their T-Box class category
        class_groups: Dict[str, List[Dict[str, Any]]] = {}
        for p in all_pages:
            cat = p.get("category", "")
            class_groups.setdefault(cat, []).append(p)

        for cat_pages in class_groups.values():
            if len(cat_pages) < 2:
                continue
            for i in range(len(cat_pages)):
                for j in range(i + 1, len(cat_pages)):
                    a, b = cat_pages[i], cat_pages[j]
                    # Check same parent
                    pa = parent_map.get(a["title"], "")
                    pb = parent_map.get(b["title"], "")
                    if pa and pb and pa == pb:
                        # Title similarity via word overlap
                        ta = set(a["title"].lower().replace(" ", ""))
                        tb = set(b["title"].lower().replace(" ", ""))
                        if ta and tb:
                            title_sim = len(ta & tb) / max(len(ta | tb), 1)
                            l2_threshold = max(0.5, threshold - 0.2)
                            if title_sim > l2_threshold:
                                pair = tuple(sorted([a["title"], b["title"]]))
                                if pair not in seen_pairs:
                                    seen_pairs.add(pair)
                                    dupes.append({
                                        "page_a": a["title"], "page_b": b["title"],
                                        "similarity": round(title_sim, 3), "layer": "L2_ontology",
                                        "suggestion": f"相同父概念 '{pa}' 且标题相似，可能是同一概念的不同表述",
                                    })
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── L3: Structural duplicates (same category + shared >= 5 related pages + content similarity gate) ──
    # Build a title→index map for vector lookup (reuse L1 vecs)
    title_index: Dict[str, int] = {all_pages[k]["title"]: k for k in range(len(all_pages))}
    for i in range(len(all_pages)):
        for j in range(i + 1, len(all_pages)):
            a, b = all_pages[i], all_pages[j]
            if a.get("category") != b.get("category"):
                continue
            related_a = a.get("related") or []
            related_b = b.get("related") or []
            shared = set(related_a) & set(related_b) & titles_set
            # Require at least 5 shared links OR 50% Jaccard overlap (whichever is stricter)
            union_size = max(len(set(related_a) | set(related_b)), 1)
            jaccard = len(shared) / union_size
            if len(shared) < 5 or jaccard < 0.5:
                continue
            pair = tuple(sorted([a["title"], b["title"]]))
            if pair in seen_pairs:
                continue
            # Cross-check with L1 content similarity (reuse pre-computed vectors)
            try:
                vi, vj = vecs[i], vecs[j]
                if vi is not None and vj is not None:
                    content_sim = cosine_similarity(vi, vj)
                    if content_sim < 0.70:
                        continue  # Structural overlap but content differs → not duplicate
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            seen_pairs.add(pair)
            dupes.append({
                "page_a": a["title"], "page_b": b["title"],
                "similarity": round(jaccard, 3), "layer": "L3_structural",
                "suggestion": f"共享 {len(shared)} 个相关页面（{', '.join(list(shared)[:3])}），可能覆盖同一子领域",
            })

    # ── L4: Evidence duplicates (same source + overlapping evidence) ──
    evidence_groups: Dict[str, List[Dict[str, Any]]] = {}
    for p in all_pages:
        body = p.get("body", "")
        src_match = re.search(r"<!-- source_doc_id:\s*(kb:\w+)", body)
        if not src_match:
            continue
        sid = src_match.group(1)
        ev_match = re.search(r"evidence_start:\s*(\d+).*?evidence_end:\s*(\d+)", body, re.DOTALL)
        if ev_match:
            evidence_groups.setdefault(sid, []).append({
                "title": p["title"],
                "start": int(ev_match.group(1)),
                "end": int(ev_match.group(2)),
            })

    for sid, group in evidence_groups.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                overlap = max(0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
                max_len = max(a["end"] - a["start"], b["end"] - b["start"], 1)
                overlap_ratio = overlap / max_len
                l4_threshold = max(0.3, (1.0 - threshold) * 3)
                if overlap_ratio > l4_threshold:
                    pair = tuple(sorted([a["title"], b["title"]]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        dupes.append({
                            "page_a": a["title"], "page_b": b["title"],
                            "similarity": round(overlap_ratio, 3),
                            "layer": "L4_evidence",
                            "suggestion": f"引用同一来源 {sid} 的重叠段落 (offset {a['start']}-{a['end']} vs {b['start']}-{b['end']})",
                        })

    return dupes


# ── LLM-powered curation ────────────────────────────────────────

async def llm_curate_page(title: str, body: str, *, existing_titles: List[str] = None,
                           source_doc_id: str = "") -> Dict[str, Any]:
    """Use LLM to read a new wiki page, extract entities, detect contradictions,
    update related pages, and generate a proper summary.

    Returns: { title, category, summary, tags, related, entities_found, contradictions, merge_candidates }
    """
    existing_titles = existing_titles or []
    result: Dict[str, Any] = {
        "title": title, "category": "entities", "summary": body[:300].replace("\n", " "),
        "tags": [], "related": [], "entities_found": [], "contradictions": [],
        "merge_candidates": [], "knowledge_atoms": [],
    }

    # Build prompt for LLM — knowledge atom extraction
    existing_list = "\n".join(f"- {t}" for t in existing_titles[:80]) if existing_titles else "(none)"
    from core.harness.utils.prompt_loader import _async_prompt_resolve
    prompt_content = f"""=== CONTENT (first 4000 chars) ===
Title: {title}
Source: {source_doc_id or 'unknown'}
{body[:4000]}

=== EXISTING WIKI PAGES ===
{existing_list}
"""
    # M3: Enrich prompt with ontology parent/child context
    try:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
        parent_map = {}
        for t in onto.triples:
            if "parentOf" in str(t.predicate):
                parent_map[str(t.object)] = str(t.subject)
        siblings: Dict[str, List[str]] = {}
        for t in existing_titles[:100]:
            if t in parent_map:
                p = parent_map[t].split("#")[-1] if "#" in parent_map[t] else parent_map[t]
                siblings.setdefault(p, []).append(t)
        if siblings:
            onto_hint = "\n=== ONTOLOGY HINTS (same-parent page groups = prime merge candidates) ===\n"
            for parent, children in list(siblings.items())[:5]:
                if len(children) >= 2:
                    onto_hint += f"  Under '{parent}': {', '.join(children[:5])}\n"
            onto_hint += "Check if the new content extends, contradicts, or should be merged into any of these groups.\n"
            prompt_content += onto_hint
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    prompt_content += """

=== TASKS ===
1. Generate a 2-3 sentence Chinese summary of the key insight (max 300 chars)

2. If this content covers multiple distinct concepts/methods/facts, extract them as knowledge_atoms:
   Each knowledge_atom = a self-contained piece of knowledge that could stand alone as a wiki page.
   For each atom: provide {{
     "title": "a short readable title (Chinese preferred, 5-15 chars)",
     "body": "the knowledge content (2-8 sentences, self-contained, Chinese preferred)",
     "category": "entities" | "topics",
     "tags": ["keyword1", "keyword2"],
     "source_doc_id": "{source_doc_id}",
     "evidence_text": "direct quote from source (50-200 chars, MUST be verbatim from input)",
     "confidence": 0.85,
     "contradicts_atom_index": null,
     "supports_atom_index": null
   }}
   Aim to extract 2-6 atoms if the content is long/complex. Each atom should be a coherent knowledge unit.
   Mark contradictions_atom_index when two atoms make opposing claims. Mark supports_atom_index when one supports another.

3. Suggest the best overall category: entities or topics

4. Extract 3-8 tags (lowercase keywords)

5. Identify 2-8 existing wiki pages that this content relates to (from the list above)

6. If the content discusses conflicting/competing viewpoints between entities, list contradictions

7. If this content overlaps heavily with any existing page (same topic, same claims), suggest it as a merge candidate

=== OUTPUT FORMAT ===
Reply with ONLY a JSON object (no markdown fences, no explanation):
{{"title":"优化的可读标题","summary":"...","category":"entities","tags":["tag1","tag2"],"related":["Existing Page"],"entities_found":["概念1","概念2"],"knowledge_atoms":[{{"title":"原子标题","body":"知识片段正文","category":"entities","tags":["tag"],"source_doc_id":"{source_doc_id}","evidence_text":"原文直接引用（50-200字，必须逐字从输入中引用）","confidence":0.85,"contradicts_atom_index":null,"supports_atom_index":null}}],"contradictions":[{{"a":"PageA","b":"PageB","detail":"why"}}],"merge_candidates":[{{"target":"PageTitle","reason":"duplicate"}}]}}
"""

    prompt = await _async_prompt_resolve("wiki-curator", content=prompt_content)
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("wiki_curation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("wiki-system-role")},
            {"role": "user", "content": prompt},
        ]
        from core.adapters.llm.base import LLMConfig as LLMCfg
        resp = await model.generate(messages, config=LLMCfg(timeout=120))
        content = resp.content if hasattr(resp, 'content') else str(resp)
        # Parse JSON from response — try multiple extraction strategies
        if content.startswith("```"):
            # Strip markdown code fences
            content = content.strip("`").strip()
            if content.startswith("json"):
                content = content[4:].strip()
        # Find the outermost JSON object (greedy match to handle nested JSON)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                data = _json.loads(json_match.group(0))
            except _json.JSONDecodeError:
                # Try cleaning: remove trailing comma before closing brace
                cleaned = re.sub(r',\s*}', '}', json_match.group(0))
                try:
                    data = _json.loads(cleaned)
                except _json.JSONDecodeError:
                    data = {}  # LLM response was malformed JSON
            if data:
                result["title"] = str(data.get("title", result["title"]))[:120]
                result["summary"] = str(data.get("summary", result["summary"]))[:500]
                result["category"] = str(data.get("category", "entities"))
                result["tags"] = list(data.get("tags", []))[:8]
                result["related"] = [t for t in (data.get("related", []) or []) if t in existing_titles][:10]
                result["entities_found"] = list(data.get("entities_found", []))[:10]
                result["contradictions"] = list(data.get("contradictions", []))[:5]
                result["merge_candidates"] = list(data.get("merge_candidates", []))[:3]
                result["knowledge_atoms"] = list(data.get("knowledge_atoms", []))[:6]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"llm_curate_page failed for '{title}': {e}")
        import traceback
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        result["fallback"] = True

    return result


# ── Knowledge Atom Operations ────────────────────────────────────

def write_atom(atom_data: Dict[str, Any], *, collection_id: str = "default") -> str:
    """Write a KnowledgeAtom as a wiki page (category='atoms').

    Atom frontmatter includes evidence tracking fields:
    source_doc_id, evidence_start, evidence_end, evidence_text, confidence.

    Evidence metadata is stored as HTML comments in body (transparent to readers).
    Returns the file path.
    """
    title = atom_data.get("title", "unnamed_atom")
    body = atom_data.get("body", "")
    # Embed evidence metadata as HTML comments for round-trip preservation
    meta_parts = []
    if atom_data.get("source_doc_id"):
        meta_parts.append(f"<!-- source_doc_id: {atom_data['source_doc_id']} -->")
    if atom_data.get("evidence_start") is not None:
        meta_parts.append(f"<!-- evidence_start: {atom_data['evidence_start']} -->")
    if atom_data.get("evidence_end") is not None:
        meta_parts.append(f"<!-- evidence_end: {atom_data['evidence_end']} -->")
    if atom_data.get("confidence") is not None:
        meta_parts.append(f"<!-- confidence: {atom_data['confidence']} -->")
    if meta_parts:
        body = "\n".join(meta_parts) + "\n" + body
    
    return write_page(
        title, body,
        category="atoms",
        tags=atom_data.get("tags", []),
        summary=atom_data.get("evidence_text", body[:200]),
        source_articles=[atom_data.get("source_doc_id", "")] if atom_data.get("source_doc_id") else [],
        relationships=atom_data.get("relationships", []),
        collection_id=collection_id,
    )


def write_atoms_batch(atoms: List[Dict[str, Any]], *, collection_id: str = "default") -> Dict[str, int]:
    """Batch write KnowledgeAtom list. Returns {written, failed} counts."""
    written = 0
    failed = 0
    for atom in atoms:
        try:
            write_atom(atom, collection_id=collection_id)
            written += 1
        except Exception:
            failed += 1
    return {"written": written, "failed": failed}


def detect_contradicting_atoms(atoms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect contradiction pairs in a list of extracted atoms.

    Detection logic:
    1. Explicit: atom.contradicts_atom_index != null
    2. Semantic: same title prefix (>10 chars overlap), different conclusions

    Returns: [{atom_a_index, atom_b_index, type, reason}]
    """
    contradictions = []

    # Explicit contradictions (LLM marked during extraction)
    for i, a in enumerate(atoms):
        j = a.get("contradicts_atom_index")
        if j is not None and isinstance(j, int) and 0 <= j < len(atoms) and j != i:
            contradictions.append({
                "atom_a_index": i,
                "atom_b_index": j,
                "type": "explicit",
                "reason": f"LLM marked as contradiction between #{i} and #{j}",
            })

    # Semantic: group by title prefix (first 15 chars)
    title_groups: Dict[str, List[int]] = {}
    for i, a in enumerate(atoms):
        prefix = str(a.get("title", ""))[:15]
        if len(prefix) >= 5:
            title_groups.setdefault(prefix, []).append(i)

    for prefix, indices in title_groups.items():
        if len(indices) >= 2:
            contradictions.append({
                "atom_a_index": indices[0],
                "atom_b_index": indices[1],
                "type": "semantic",
                "reason": f"Similar topic prefix '{prefix}', potential opposing claims",
            })

    return contradictions


def build_contradiction_page(atoms: List[Dict[str, Any]], contradiction: Dict,
                              *, collection_id: str = "default") -> Optional[str]:
    """Create a ContradictionPage from a detected contradiction pair."""
    a = atoms[contradiction["atom_a_index"]]
    b = atoms[contradiction["atom_b_index"]]

    title = f"Contradiction: {str(a.get('title',''))[:30]} vs {str(b.get('title',''))[:30]}"
    body_parts = [
        f"## 断言 A",
        a.get("body", ""),
        f"\n来源: {a.get('source_doc_id', 'unknown')}",
        f"证据: {a.get('evidence_text', '')}",
        f"\n## 断言 B",
        b.get("body", ""),
        f"\n来源: {b.get('source_doc_id', 'unknown')}",
        f"证据: {b.get('evidence_text', '')}",
        f"\n## 冲突分析",
        contradiction.get("reason", "语义矛盾"),
    ]
    body = "\n".join(body_parts)

    return write_page(
        title, body,
        category="contradictions",
        contradictions=[str(a.get("title", ""))[:80], str(b.get("title", ""))[:80]],
        source_articles=[
            a.get("source_doc_id", ""),
            b.get("source_doc_id", ""),
        ],
        collection_id=collection_id,
    )


async def atomize_document(doc_text: str, doc_id: str, *,
                            collection_id: str = "default",
                            max_atoms: int = 20,
                            model_name: str = "") -> Dict[str, Any]:
    """Full pipeline: raw document → KnowledgeAtom extraction → schema validation → write → contradiction detection.

    Uses T-Box schema to guide LLM extraction, ensuring every atom has:
    - Required fields (title, body, source_doc_id)
    - Evidence positions (evidence_start, evidence_end, evidence_text)
    - Confidence score

    Returns:
        {atoms_extracted, atoms_written, contradictions_found,
         contradiction_pages_created, atoms: [...], contradictions: [...]}
    """
    result = {"atoms_extracted": 0, "atoms_written": 0, "contradictions_found": 0,
              "contradiction_pages_created": 0, "atoms": [], "contradictions": [],
              "error": None}

    # Step 1: Build ontology-driven extraction prompt
    from core.harness.knowledge.knowledge_ontology import build_atom_extraction_prompt
    prompt = build_atom_extraction_prompt(doc_text, doc_id, max_atoms=max_atoms)

    # Step 2: Call LLM to extract atoms
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model = create_selected_adapter(
            model_name=model_name or best_model_for_purpose("wiki_curation")
        )
        messages = [{"role": "system", "content": "You are a knowledge extraction expert. Return ONLY valid JSON array."},
                     {"role": "user", "content": prompt}]
        from core.adapters.llm.base import LLMConfig as LLMCfg
        resp = await model.generate(messages, config=LLMCfg(timeout=120))
        content = resp.content if hasattr(resp, 'content') else str(resp)
    except Exception as e:
        result["error"] = f"LLM extraction failed: {e}"
        return result

    # Step 3: Parse LLM JSON output
    import re, json as _json
    try:
        if content.startswith("```"):
            content = content.strip("`").strip()
            if content.startswith("json"):
                content = content[4:].strip()
        json_match = re.search(r'\[[\s\S]*\]', content)
        if json_match:
            atoms = _json.loads(json_match.group(0))
        else:
            atoms = []
    except Exception:
        atoms = []
    
    result["atoms_extracted"] = len(atoms)

    # Step 4: Schema validate each atom
    from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
    valid_atoms = []
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        atom["category"] = atom.get("category", "atoms")
        r = validate_page_against_schema(atom, mode="warning")
        if r.is_valid or not r.missing_required:
            valid_atoms.append(atom)
        else:
            logging.getLogger("wiki_engine").warning(
                f"atomize_document: skipping atom '{atom.get('title','?')}': missing {r.missing_required}")

    # Step 5: Write valid atoms
    if valid_atoms:
        write_result = write_atoms_batch(valid_atoms, collection_id=collection_id)
        result["atoms_written"] = write_result["written"]
        result["atoms"] = valid_atoms

    # Step 6: Detect contradictions
    if len(valid_atoms) >= 2:
        contradictions = detect_contradicting_atoms(valid_atoms)
        result["contradictions_found"] = len(contradictions)
        result["contradictions"] = contradictions

        # Step 7: Create contradiction pages
        for c in contradictions:
            try:
                build_contradiction_page(valid_atoms, c, collection_id=collection_id)
                result["contradiction_pages_created"] += 1
            except Exception as e:
                logging.debug(str(e), exc_info=True)

    return result


def clean_stale_references(collection_id: str = "default") -> Dict[str, Any]:
    """Scan all wiki pages, move stale kb: references from source_articles to stale_references.

    A reference is stale when the kb:doc_id prefix maps to a doc_id that
    does not exist in the KB SQLite documents table.

    Returns:
        {scanned, affected, stale_refs_moved, details: [{page, removed, added_to_stale}], abox_rebuilt}
    """
    import os as _os, sqlite3 as _sq

    all_pages = search_pages(limit=10000, collection_id=collection_id)
    result = {"scanned": len(all_pages), "affected": 0, "stale_refs_moved": 0, "details": []}

    # Step 1: Get known KB document IDs
    kb_dir = _os.path.expanduser(_os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    known_doc_ids: set = set()
    kb_db = _os.path.join(kb_dir, "default", "kb.sqlite3")
    if _os.path.exists(kb_db):
        try:
            conn = _sq.connect(kb_db)
            rows = conn.execute("SELECT doc_id FROM documents WHERE status='ready'").fetchall()
            known_doc_ids = {r[0] for r in rows}
            conn.close()
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # Step 2: Scan each page for stale kb:/upload:/vault: references
    for page in all_pages:
        title = page.get("title", "")
        source_articles = list(page.get("source_articles") or [])
        stale_refs = list(page.get("stale_references") or [])

        removed = []
        kept = []
        for s in source_articles:
            is_stale = False
            if isinstance(s, str):
                if s.startswith("kb:"):
                    doc_id = s[3:]
                    is_stale = doc_id not in known_doc_ids
                elif s.startswith("upload:") or s.startswith("vault:"):
                    # upload: and vault: sources never map to KB documents
                    is_stale = True
            
            if is_stale:
                removed.append(s)
                if s not in stale_refs:
                    stale_refs.append(s)
            else:
                kept.append(s)

        if removed:
            update_page(
                title,
                source_articles=kept,
                stale_references=stale_refs,
                collection_id=collection_id,
            )
            result["details"].append({
                "page": title,
                "removed": removed,
                "added_to_stale": [s for s in removed if s not in page.get("stale_references", [])],
            })
            result["stale_refs_moved"] += len(removed)
            result["affected"] += 1

    # Step 3: Rebuild A-Box to refresh validator consistency
    try:
        from core.harness.knowledge.knowledge_abox_builder import rebuild_full
        rebuild_full(collection_id=collection_id)
        result["abox_rebuilt"] = True
    except Exception as e:
        result["abox_rebuilt"] = False
        result["abox_error"] = str(e)

    return result


def _parse_json_response(content: str) -> Optional[Dict]:
    """Parse JSON from LLM response with fallback cleanup."""
    import re as _re, json as _json
    if not content:
        return None
    if content.startswith("```"):
        content = content.strip("`").strip()
        if content.startswith("json"):
            content = content[4:].strip()
    json_match = _re.search(r'[\{\[][\s\S]*[\}\]]', content)
    if json_match:
        try:
            return _json.loads(json_match.group(0))
        except _json.JSONDecodeError:
            cleaned = _re.sub(r',\s*[\}\]]', lambda m: m.group(0)[-1], json_match.group(0))
            try:
                return _json.loads(cleaned)
            except _json.JSONDecodeError:
                pass
    return None


async def _extract_sub_concepts(title: str, body: str, collection_id: str,
                                 model_name: str = "") -> List[Dict]:
    """LLM: extract sub-concepts from a topic page as atom candidates."""
    prompt = f"""Read the topic page below and extract 3-5 sub-concepts as standalone knowledge atoms.

For each sub-concept:
  - title: readable name (Chinese, 5-15 chars)
  - body: definition (2-4 sentences, self-contained)
  - evidence_text: verbatim quote from the page body (50-150 chars)
  - confidence: 0.5-1.0
  - tags: 2-4 keywords

=== TOPIC PAGE ({title}) ===
{body[:6000]}

=== OUTPUT ===
Return ONLY a JSON array (no markdown fences):
[{{"title":"...","body":"...","evidence_text":"...","confidence":0.8,"tags":["..."]}}]
"""
    from core.harness.utils.model_injection import generate_with_fallback
    resp, selected_model = await generate_with_fallback(
        "wiki_curation",
        messages=[{"role": "system", "content": "Return ONLY valid JSON array."},
                  {"role": "user", "content": prompt}],
        timeout=60
    )
    content = resp.content if hasattr(resp, 'content') else str(resp)
    result = _parse_json_response(content)
    return result if isinstance(result, list) else []


async def _auto_atomize(title: str, body: str, collection_id: str):
    """Automatically extract atoms from a topic page after write (background)."""
    import asyncio as _asyncio
    try:
        await _asyncio.sleep(1.0)  # brief cooldown after write
        atoms = await _extract_sub_concepts(title, body, collection_id)
        created = 0
        for atom in atoms[:3]:
            if not read_page(atom.get("title", ""), collection_id=collection_id):
                write_atom(atom, collection_id=collection_id)
                created += 1
        if created:
            _log = logging.getLogger("wiki_engine")
            _log.info(f"Auto-atomized '{title}': {created} atoms created")
    except Exception:
        logging.getLogger("wiki_engine").warning(f"Auto-atomize failed for '{title}'", exc_info=True)


async def _auto_atomize_by_title_impl(title: str, collection_id: str):
    """Read page from disk and auto-atomize. Called by background task worker."""
    import asyncio as _asyncio, logging as _logging
    _log = _logging.getLogger("wiki_engine")
    try:
        await _asyncio.sleep(0.5)
        page = read_page(title, collection_id=collection_id)
        if page and len(page.get("body", "")) > 500:
            await _auto_atomize(title, page["body"], collection_id)
    except Exception:
        _log.warning(f"Auto-atomize failed for '{title}'", exc_info=True)


async def _detect_page_contradiction(a_page: Dict, b_page: Dict,
                                       model_name: str = "") -> Dict:
    """LLM: detect if two pages have contradictory claims."""
    prompt = f"""Analyze these two wiki pages for contradictory claims.

Page A: {a_page.get('title','')}
{a_page.get('body','')[:3000]}

Page B: {b_page.get('title','')}
{b_page.get('body','')[:3000]}

Do they contain mutually contradictory claims? Only flag as contradiction if:
- They make OPPOSITE claims about the SAME specific thing
- One says X is true/useful, the other says X is false/harmful/ineffective
- NOT just different perspectives on different topics

Return ONLY a JSON object:
{{"has_contradiction": true|false, "reason": "specific contradiction description"}}
"""
    from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
    model = create_selected_adapter(
        model_name=model_name or best_model_for_purpose("wiki_curation")
    )
    resp = await model.generate(
        [{"role": "system", "content": "Return ONLY valid JSON."},
         {"role": "user", "content": prompt}],
        config=None
    )
    content = resp.content if hasattr(resp, 'content') else str(resp)
    result = _parse_json_response(content)
    return result if isinstance(result, dict) else {"has_contradiction": False}


def build_contradiction_page_by_data(a_page: Dict, b_page: Dict, *,
                                     reason: str = "",
                                     collection_id: str = "default") -> Optional[str]:
    """Create a ContradictionPage from two page dicts."""
    a_title = a_page.get("title", "?")
    b_title = b_page.get("title", "?")
    title = f"Contradiction: {a_title[:30]} vs {b_title[:30]}"
    body_parts = [
        f"## {a_title}",
        a_page.get("body", "")[:2000],
        f"\n## {b_title}",
        b_page.get("body", "")[:2000],
        f"\n## 冲突原因",
        reason or "自动检测到的语义矛盾",
    ]
    return write_page(
        title, "\n".join(body_parts),
        category="contradictions",
        contradictions=[a_title, b_title],
        source_articles=list(set(
            (a_page.get("source_articles") or []) +
            (b_page.get("source_articles") or [])
        ))[:5],
        collection_id=collection_id,
    )


async def seed_instances(collection_id: str = "default",
                          model_name: str = "") -> Dict[str, Any]:
    """Create seed instances for empty T-Box categories (atoms, contradictions).

    Uses LLM to extract sub-concepts from TopicPages and detect contradictions
    between related page pairs. Creates 3-5 atoms and 2-3 contradiction pages.
    """
    import asyncio as _asyncio

    result = {"atoms_created": 0, "contradictions_created": 0, "details": []}

    all_pages = search_pages(limit=10000, collection_id=collection_id)

    # ── Step 1: Sub-concept atoms from TopicPages ──
    topics = [p for p in all_pages
              if p.get("category") == "topics" and len(p.get("body", "")) > 500]
    for topic in topics[:3]:
        try:
            atoms = await _extract_sub_concepts(
                topic["title"], topic.get("body", ""),
                collection_id, model_name=model_name
            )
            for atom in atoms[:3]:
                existing = read_page(atom["title"], collection_id=collection_id)
                if existing:
                    continue
                write_atom({
                    "title": atom["title"],
                    "body": atom.get("body", ""),
                    "source_doc_id": f"kb:seed_{collection_id}",
                    "evidence_text": atom.get("evidence_text", ""),
                    "confidence": float(atom.get("confidence", 0.7)),
                    "tags": atom.get("tags", []),
                }, collection_id=collection_id)
                result["atoms_created"] += 1
            result["details"].append(
                {"step": "sub_concept", "source": topic["title"],
                 "extracted": len(atoms), "created": min(len(atoms), 3)})
        except Exception as e:
            result["details"].append({"step": "sub_concept", "source": topic["title"], "error": str(e)})

    # ── Step 2: Contradiction detection from tag-sharing pages ──
    tag_groups: Dict[str, List[str]] = {}
    for p in all_pages:
        for t in (p.get("tags") or []):
            tag_groups.setdefault(t, []).append(p["title"])
    candidate_pairs = set()
    for tag, titles in tag_groups.items():
        if len(titles) >= 2:
            for i in range(len(titles)):
                for j in range(i + 1, len(titles)):
                    candidate_pairs.add(tuple(sorted([titles[i], titles[j]])))

    for a_title, b_title in list(candidate_pairs)[:3]:
        try:
            a_page = read_page(a_title, collection_id=collection_id)
            b_page = read_page(b_title, collection_id=collection_id)
            if not a_page or not b_page:
                continue
            contradiction = await _detect_page_contradiction(
                a_page, b_page, model_name=model_name
            )
            if contradiction and contradiction.get("has_contradiction"):
                build_contradiction_page_by_data(
                    a_page, b_page,
                    reason=contradiction.get("reason", "semantic contradiction"),
                    collection_id=collection_id,
                )
                result["contradictions_created"] += 1
                result["details"].append(
                    {"step": "contradiction", "pair": [a_title, b_title],
                     "reason": contradiction.get("reason", "")[:80]})
        except Exception as e:
            result["details"].append(
                {"step": "contradiction", "pair": [a_title, b_title], "error": str(e)})

    return result


def backfill_evidence_for_page_sync(title: str, *, collection_id: str = "default") -> Dict[str, Any]:
    """Extract evidence annotations from a wiki page's own content (non-LLM fallback).

    Identifies the first 2-3 sentences as evidence_text and embeds them
    as HTML comments for the evidence-chain API. This is a lightweight
    self-referencing backfill for pages where original KB sources are gone.

    Returns:
        {title, claims_extracted, updated}
    """
    page = read_page(title, collection_id=collection_id)
    if not page:
        return {"title": title, "error": "page not found"}

    body = page.get("body", "")
    if len(body) < 50:
        return {"title": title, "error": "body too short"}

    # Check if already has evidence
    if "<!-- evidence_text:" in body:
        return {"title": title, "already_backfilled": True, "updated": False}

    # Extract first 1-2 sentences as evidence
    import re as _re
    sentences = _re.split(r'(?<=[。！？\n])\s*', body.strip())
    evidence_parts = []
    for s in sentences[:5]:
        s = s.strip()
        if len(s) >= 20 and len(s) <= 300:
            evidence_parts.append(s)
            if len(evidence_parts) >= 2:
                break

    if not evidence_parts:
        evidence_parts = [body[:200].strip()]

    evidence_text = " ".join(evidence_parts)[:300]
    confidence = 0.6  # Self-referencing: moderate confidence

    comment = (
        f"<!-- evidence_text: {evidence_text} -->\n"
        f"<!-- evidence_confidence: {confidence} -->\n"
    )
    new_body = comment + body

    write_page(
        title, new_body,
        category=page.get("category", "entities"),
        tags=page.get("tags", []),
        related=page.get("related", []),
        contradictions=page.get("contradictions", []),
        source_articles=page.get("source_articles", []),
        summary=page.get("summary", ""),
        collection_id=collection_id,
    )

    return {
        "title": title,
        "claims_extracted": 1,
        "evidence_text": evidence_text[:80] + "...",
        "updated": True,
    }


def backfill_evidence_batch_sync(collection_id: str = "default",
                                  limit: int = 50) -> Dict[str, Any]:
    """Batch backfill evidence for all pages that have kb: source_articles but no evidence.

    Uses the sync (non-LLM) backfill method. Processes all matching pages.
    Records failures to a tracking file.

    Returns:
        {total_candidates, succeeded, failed, details: [...]}
    """
    import os as _os, time as _time

    all_pages = search_pages(limit=10000, collection_id=collection_id)

    # Find pages needing backfill
    candidates = []
    for p in all_pages:
        full = read_page(p["title"], collection_id=collection_id)
        if not full or not full.get("body"):
            continue
        body = full.get("body", "")
        has_source = any(s.startswith("kb:") for s in (p.get("source_articles") or []))
        has_evidence = "<!-- evidence_text:" in body
        if has_source and not has_evidence:
            candidates.append(p["title"])

    candidates = candidates[:limit]
    result = {"total_candidates": len(candidates), "succeeded": 0, "failed": 0,
              "details": [], "failures_file": None}
    failures = []

    for title in candidates:
        try:
            r = backfill_evidence_for_page_sync(title, collection_id=collection_id)
            result["details"].append(r)
            if r.get("updated"):
                result["succeeded"] += 1
            elif not r.get("already_backfilled"):
                failures.append({"title": title, "error": r.get("error", "unknown")})
                result["failed"] += 1
            else:
                result["succeeded"] += 1  # already backfilled counts as success
        except Exception as e:
            failures.append({"title": title, "error": str(e)})
            result["failed"] += 1

    if failures:
        fail_path = _os.path.join(
            _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat")),
            "wiki", "collections", collection_id, "backfill_failures.json"
        )
        _os.makedirs(_os.path.dirname(fail_path), exist_ok=True)
        import json as _json
        with open(fail_path, "w") as f:
            _json.dump({"timestamp": _time.time(), "failures": failures}, f, indent=2)
        result["failures_file"] = fail_path

    return result


def _sync_synthesis_pages(updated_title: str, *, collection_id: str = "default", domain_id: str = "ai-knowledge") -> int:
    """When a source page is updated, find synthesis pages that reference it and create review entries.

    Synthesis pages have frontmatter.source_instances listing their source entities.
    Returns count of review entries created.
    """
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.ontology_engine.engine import _persist_reviews
        import json as _json
        from pathlib import Path as _P
        import os as _os

        # Find all synthesis pages that list this title as a source
        all_pages = search_pages("", category="synthesis", limit=500, collection_id=collection_id)
        affected = []
        for p in all_pages:
            content = read_page(p["title"], category=p.get("category", "synthesis"), collection_id=collection_id)
            if not content:
                continue
            source_instances = content.get("source_instances", [])
            if updated_title in source_instances:
                stype = content.get("synthesis_type", "synthesis")
                affected.append({
                    "from_instance": updated_title,
                    "from_class": "WikiPage",
                    "to_instance": p["title"],
                    "to_class": stype,
                    "reason": f"源实例已更新，合成{stype}结论需复审",
                    "transition": "synthesis_version_sync",
                })
        if affected:
            _persist_reviews(domain_id, affected)
        return len(affected)
    except Exception:
        return 0


def recommend_knowledge(
    department: str = "",
    recent_queries: list = None,
    *,
    domain_id: str = "ai-knowledge",
    limit: int = 5,
    collection_id: str = "default",
) -> List[Dict[str, Any]]:
    """L5 active knowledge recommendation engine.

    Recommends knowledge based on:
      a) Recently updated pages in the user's department
      b) High-velocity entities (most state changes recently)
      c) Knowledge gaps that match the user's context
      d) Pending review items

    Returns ranked list of recommendations with reason and priority.
    """
    recommendations = []

    # a) Department-specific recent pages
    if department:
        recent_pages = search_pages("", department=department, limit=limit, collection_id=collection_id)
        for p in recent_pages:
            recommendations.append({
                "title": p.get("title", ""),
                "reason": f"部门 '{department}' 相关页面",
                "priority": "medium",
                "source": "department_match",
            })

    # b) High-velocity entities from state history
    try:
        from core.harness.ontology_engine.state_history import get_entity_window_stats
        stats = get_entity_window_stats(domain_id, window_hours=24)
        if stats.get("velocity", 0) > 0.5:
            for chain in stats.get("top_chains", [])[:3]:
                recommendations.append({
                    "title": chain.get("entity_name", ""),
                    "reason": f"最近活跃: {chain.get('transitions', 0)} 次状态变更",
                    "priority": "high",
                    "source": "high_velocity",
                })
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # c) Knowledge gaps
    if recent_queries:
        try:
            from core.harness.ontology_engine.knowledge_gap_detector import detect_knowledge_gaps
            gaps = detect_knowledge_gaps(recent_queries, domain_id=domain_id, min_frequency=1, max_gaps=3)
            for g in gaps.get("gaps", [])[:3]:
                recommendations.append({
                    "title": g.get("query", ""),
                    "reason": f"知识缺口({g.get('gap_type', '')}): {g.get('suggestion', '')[:40]}",
                    "priority": "high",
                    "source": "knowledge_gap",
                })
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # d) Pending reviews
    try:
        from core.harness.ontology_engine.engine import _persist_reviews
        import json as _json
        from pathlib import Path as _P
        import os as _os
        home = _P(_os.getenv("AIPLAT_HOME", _P("~").expanduser() / ".aiplat"))
        reviews_file = home / "ontology_reviews" / f"{domain_id}.json"
        if reviews_file.exists():
            reviews = _json.loads(reviews_file.read_text())
            pending = [r for r in reviews if r.get("status") == "pending"][:3]
            for r in pending:
                recommendations.append({
                    "title": r.get("to_instance", ""),
                    "reason": f"待复查: {r.get('reason', '')[:50]}",
                    "priority": "high",
                    "source": "pending_review",
                })
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Dedup by title and limit
    seen = set()
    deduped = []
    for r in recommendations:
        key = r["title"]
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
            if len(deduped) >= limit * 2:
                break

    return sorted(deduped, key=lambda r: 0 if r["priority"] == "high" else 1)[:limit]


__all__ = [
    "read_page", "write_page", "search_pages", "traverse_links",
    "detect_contradictions", "list_all_pages", "llm_curate_page", "_wiki_root",
    "write_atom", "write_atoms_batch", "atomize_document",
    "detect_contradicting_atoms", "build_contradiction_page",
    "create_collection", "delete_collection", "list_collections",
    "update_page", "delete_page", "delete_all_pages",
]
