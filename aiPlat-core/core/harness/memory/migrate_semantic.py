#!/usr/bin/env python3
"""
Migration: split single memory_semantic.sqlite3 into per-tenant files.
Phase 18.4 — one-time run in deployment pipeline.

Usage:
  python -m core.harness.memory.migrate_semantic --dry-run
  python -m core.harness.memory.migrate_semantic
"""

import json, logging, os, sqlite3, sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_semantic")

SRC_DB = os.path.expanduser("~/.aiplat/memory_semantic.sqlite3")
DST_DIR = os.path.expanduser("~/.aiplat")


def run(dry_run: bool = True):
    if not os.path.exists(SRC_DB):
        logger.info("No source DB found — nothing to migrate")
        return

    src = sqlite3.connect(SRC_DB)
    src.row_factory = sqlite3.Row
    rows = src.execute(
        "SELECT key, content, metadata_json, embedding, access_count, "
        "expires_at, is_deleted FROM semantic_memories"
    ).fetchall()
    src.close()

    groups: dict = {}
    orphans = 0
    total = 0
    for r in rows:
        meta = json.loads(r["metadata_json"] or "{}")
        tid = meta.get("tenant_id") or "default"
        if not meta.get("tenant_id"):
            orphans += 1
        groups.setdefault(tid, []).append(r)
        total += 1

    logger.info("Migrating %d records across %d tenants (%d orphans → default)",
                total, len(groups), orphans)

    for tid, recs in sorted(groups.items()):
        if tid == "default":
            dst_path = SRC_DB
        else:
            dst_path = os.path.join(DST_DIR, f"memory_semantic_{tid}.sqlite3")

        if dry_run:
            logger.info("[DRY-RUN] tenant=%s: %d records → %s", tid, len(recs), dst_path)
            continue

        dst = sqlite3.connect(dst_path)
        dst.execute("""CREATE TABLE IF NOT EXISTS semantic_memories (
            key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            embedding BLOB,
            created_at TEXT,
            accessed_at TEXT,
            access_count INTEGER DEFAULT 0,
            expires_at TEXT,
            is_deleted INTEGER DEFAULT 0
        )""")
        for r in recs:
            dst.execute(
                "INSERT OR REPLACE INTO semantic_memories VALUES (?,?,?,?,?,?,?,?,?)",
                (r["key"], r["content"], r["metadata_json"], r["embedding"],
                 r["access_count"] or 0, r["expires_at"], r["is_deleted"] or 0,
                 None, None),
            )
        dst.commit()
        dst.close()
        logger.info("[PARTITION] tenant=%s: %d records → %s", tid, len(recs), dst_path)

    if not dry_run and os.path.exists(SRC_DB):
        os.rename(SRC_DB, SRC_DB + ".bak")
        logger.info("Source DB backed up to %s.bak", SRC_DB)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
