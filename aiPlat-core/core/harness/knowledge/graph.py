"""
Knowledge Graph — lightweight entity-relation graph for RAG enhancement.

Stores entity-relation triples in SQLite and provides graph-enhanced
retrieval via entity linking (query → entities → related documents).

Architecture:
  - Core layer, zero external dependencies
  - Uses shared KB SQLite (same DB as platform)
  - Entity extraction via LLM during ingest (async, non-blocking)
  - Graph search via entity linking at query time
"""
from __future__ import annotations
import logging

import json as _json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


_GRAPH_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_graph (
    tenant_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    relation TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    meta_json TEXT,
    PRIMARY KEY (tenant_id, doc_id, source_entity, relation, target_entity)
);
CREATE INDEX IF NOT EXISTS idx_kb_graph_entity ON kb_graph(tenant_id, source_entity);
CREATE INDEX IF NOT EXISTS idx_kb_graph_doc ON kb_graph(tenant_id, doc_id);
"""


def _graph_db_path(tenant_id: str = "default") -> str:
    base = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    return os.path.join(base, tenant_id or "default", "kb.sqlite3")


def _ensure_graph_schema(conn: sqlite3.Connection) -> None:
    try:
        conn.executescript(_GRAPH_SCHEMA)
        conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)


async def extract_entities(
    text: str,
    doc_id: str = "",
    tenant_id: str = "default",
) -> List[Dict[str, str]]:
    """Extract entity-relation triples from text via LLM.
    Returns list of {source_entity, relation, target_entity}.
    """
    if len(text) < 50:
        return []
    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose
        prompt = (
            "Extract key entities and their relationships from the text below. "
            "Output ONLY a JSON array of {source_entity, relation, target_entity} objects. "
            "Focus on named entities (people, organizations, products, technologies, concepts) "
            "and their clear relationships. Limit to 8 most important triples.\n\n"
            f"Text: {text[:3000]}"
        )
        resp = await sys_llm_generate(
            None,
            [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("chat"),
            temperature=0.1,
            max_tokens=800,
        )
        raw = getattr(resp, "content", "") or str(resp)
        # Extract JSON array
        import re as _re
        m = _re.search(r"\[.*\]", raw, _re.DOTALL)
        if m:
            triples = _json.loads(m.group(0))
            if isinstance(triples, list):
                # Store in graph
                _store_triples(tenant_id, doc_id, triples)
                return triples
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return []


def _store_triples(tenant_id: str, doc_id: str, triples: list) -> None:
    """Store entity-relation triples in kb_graph table."""
    if not triples:
        return
    db_path = _graph_db_path(tenant_id)
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA busy_timeout=3000")
        _ensure_graph_schema(conn)
        for t in triples:
            if isinstance(t, dict):
                conn.execute(
                    "INSERT OR IGNORE INTO kb_graph(tenant_id,doc_id,source_entity,relation,target_entity,meta_json) VALUES(?,?,?,?,?,?)",
                    (tenant_id, doc_id,
                     str(t.get("source_entity", "")).strip(),
                     str(t.get("relation", "")).strip(),
                     str(t.get("target_entity", "")).strip(),
                     "{}"),
                )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.debug(str(e), exc_info=True)


def graph_enhance_query(
    query: str,
    tenant_id: str = "default",
    doc_ids: Optional[List[str]] = None,
    max_related: int = 5,
) -> List[Dict[str, Any]]:
    """Expand query via entity linking: find related documents through graph.

    Returns list of {doc_id, source_entity, relation, target_entity}.
    """
    db_path = _graph_db_path(tenant_id)
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA busy_timeout=3000")
        conn.row_factory = sqlite3.Row
        _ensure_graph_schema(conn)
        # Search for entities matching query terms in graph
        tokens = _extract_key_terms(query)
        results = []
        for token in tokens[:3]:
            where = " AND doc_id IN ({})".format(",".join("?" * len(doc_ids))) if doc_ids else ""
            params = [tenant_id, f"%{token}%"] + (doc_ids or [])
            rows = conn.execute(
                f"SELECT DISTINCT doc_id, source_entity, relation, target_entity FROM kb_graph WHERE tenant_id=? AND (source_entity LIKE ? OR target_entity LIKE ?) {where} LIMIT ?",
                (tenant_id, f"%{token}%", f"%{token}%", *([*doc_ids] if doc_ids else []), max_related * 2),
            ).fetchall()
            for r in rows:
                results.append(dict(r))
        conn.close()
        return results[:max_related]
    except Exception:
        return []


def _extract_key_terms(text: str) -> List[str]:
    """Extract key terms for entity matching."""
    import re as _re
    return _re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}', text.lower())
