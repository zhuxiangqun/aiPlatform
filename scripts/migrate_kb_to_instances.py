#!/usr/bin/env python3
"""
Batch migration: 已有 KB 文档 → 本体实例 → Wiki 页面

Usage:
  python3 scripts/migrate_kb_to_instances.py                    # 预览模式（不写）
  python3 scripts/migrate_kb_to_instances.py --write            # 执行写入
  python3 scripts/migrate_kb_to_instances.py --domain ai-knowledge --collection default
"""

from __future__ import annotations

import asyncio
import json as _json
import os as _os
import sys as _sys
from pathlib import Path as _Path

PROJECT_ROOT = _Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(PROJECT_ROOT / "aiPlat-core"))
_sys.path.insert(0, str(PROJECT_ROOT / "aiPlat-infra"))


async def load_kb_documents() -> list[dict]:
    """Load documents from KB SQLite databases."""
    import sqlite3

    kb_dirs = [
        _Path(_os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "kb" / "tenants",
        _Path.home() / ".aiplat" / "kb" / "tenants",
    ]
    docs = []
    for kb_dir in kb_dirs:
        if not kb_dir.exists():
            continue
        for tenant_dir in kb_dir.glob("*"):
            if not tenant_dir.is_dir():
                continue
            db_path = tenant_dir / "kb.sqlite3"
            if not db_path.exists():
                continue
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT id, title, content_text, metadata FROM documents WHERE content_text IS NOT NULL LIMIT 50"
                ).fetchall()
                for row in rows:
                    d = dict(row)
                    content = d.get("content_text", "") or ""
                    if len(content) > 100:
                        docs.append({
                            "doc_id": f"kb:{d.get('id', '')}",
                            "title": d.get("title", "") or "Untitled",
                            "text": content[:5000],
                            "metadata": d.get("metadata", "{}"),
                        })
            except sqlite3.OperationalError:
                pass
            finally:
                conn.close()
    return docs


async def load_wiki_documents(collection: str = "default") -> list[dict]:
    """Load existing wiki pages as document sources."""
    from core.harness.knowledge.wiki_engine import search_pages, read_page
    pages = search_pages(limit=100, collection_id=collection)
    docs = []
    for p in (pages or []):
        full = read_page(p["title"], collection_id=collection) or {}
        body = full.get("body", "") or ""
        if len(body) > 100:
            docs.append({
                "doc_id": f"wiki:{p['title']}",
                "title": p["title"],
                "text": body[:5000],
                "metadata": str(full.get("fm", {})),
            })
    return docs


async def load_wiki_pages(collection: str = "default") -> set[str]:
    """Get existing wiki page titles to avoid duplicates."""
    from core.harness.knowledge.wiki_engine import search_pages
    pages = search_pages(limit=10000, collection_id=collection)
    return {p["title"] for p in (pages or [])}


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="KB文档/Wiki页面 → 本体实例迁移")
    parser.add_argument("--write", action="store_true", help="实际写入Wiki页面")
    parser.add_argument("--domain", default="ai-knowledge", help="域本体ID")
    parser.add_argument("--collection", default="default", help="Wiki集合")
    parser.add_argument("--limit", type=int, default=10, help="最多处理文档数")
    parser.add_argument("--wiki", action="store_true", help="从已有Wiki页面读取内容（而非KB文档）")
    parser.add_argument("--classify-only", action="store_true", help="仅运行类映射，跳过LLM属性提取")
    args = parser.parse_args()

    # Load domain engine
    from core.harness.ontology_engine.engine import load_engine
    engine = load_engine(args.domain)
    if engine is None:
        print(f"Domain '{args.domain}' not found")
        return 1

    if args.wiki:
        docs = await load_wiki_documents(args.collection)
        print(f"Found {len(docs)} Wiki pages with content")
    else:
        docs = await load_kb_documents()
        print(f"Found {len(docs)} KB documents")
    docs = docs[: args.limit]

    # Get existing wiki page titles
    existing = await load_wiki_pages(args.collection)
    print(f"Existing Wiki pages: {len(existing)}")

    total_instances = 0
    total_written = 0
    total_skipped = 0

    for doc in docs:
        print(f"\n📄 {doc['title'][:60]}...")

        if args.classify_only:
            # Fast path: only ClassMapper, no LLM
            from core.harness.ontology_engine.class_mapper import ClassMapper
            mapper = ClassMapper(engine._domain)
            cls_name = mapper.classify_text(doc["text"], threshold=0.5)
            if cls_name:
                print(f"  📝 → {cls_name} ({doc['title']})")
            else:
                print(f"  ❓ → no class matched")
            continue

        chunks = [{"id": f"{doc['doc_id']}-0", "text": doc["text"], "entities": []}]
        result = await engine.process_chunks(chunks, doc_id=doc["doc_id"])

        for inst in result.instances:
            total_instances += 1
            title = inst.get("frontmatter", {}).get("title", "")
            if not title or title in existing:
                total_skipped += 1
                print(f"  ⏭ {inst['class_name']}: {title or '(no title)'} (skipped)")
                continue

            if args.write:
                from core.harness.knowledge.wiki_engine import write_page
                fm = inst.get("frontmatter", {})
                try:
                    await write_page(
                        title=title,
                        body=str(fm.get("description", "") or fm.get("body", "") or ""),
                        category=fm.get("category", "entities"),
                        collection_id=args.collection,
                        tags=list(fm.get("tags", []) or []),
                        summary=str(fm.get("summary", "") or ""),
                    )
                    total_written += 1
                    existing.add(title)
                    print(f"  ✅ {inst['class_name']}: {title}")
                except Exception as e:
                    print(f"  ❌ {inst['class_name']}: {title} ({e})")
            else:
                print(f"  📝 {inst['class_name']}: {title} (dry-run, not written)")

    print(f"\n{'='*50}")
    print(f"Total: {total_instances} instances from {len(docs)} docs")
    print(f"Written: {total_written} | Skipped: {total_skipped}")
    if not args.write:
        print("\n🔍 DRY RUN: use --write to actually write Wiki pages")
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
