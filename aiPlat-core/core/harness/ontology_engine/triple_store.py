"""
OntologyTripleStore — unified cross-graph triple storage and query engine.

Bridges the 5 isolated graphs (GraphIndex, CapabilityGraph, CodeGraph, Wiki, KB)
via a single (subject, predicate, object) triple store backed by SQLite.

Supports BFS multi-hop traversal for cross-domain impact analysis.

Usage:
    store = get_triple_store()
    store.add("urn:aiplat:agent:rag_agent", "uses_skill", "urn:aiplat:skill:knowledge_retrieve")
    impact = store.get_downstream("urn:aiplat:agent:rag_agent", depth=3)
    sources = store.get_upstream("urn:aiplat:skill:knowledge_retrieve", depth=3)

CLI:
    python -m core.harness.ontology_engine.triple_store urn:aiplat:agent:rag_agent
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TRIPLE_TYPES = {
    "uses_skill":           "Agent → Skill",
    "uses_tool":            "Agent → Tool",
    "uses_model":           "Agent → Model",
    "calls_syscall":        "Skill → Syscall",
    "requires_permission":  "Skill → 权限要求",
    "depends_on":           "Pipeline → 上游阶段",
    "depends_on_wiki":      "Pipeline → Wiki 页面",
    "depends_on_kb":        "Wiki → KB Document",
    "produces_artifact":    "Pipeline → 产物",
    "member_of_phase":      "Agent → Pipeline Phase",
    # v1.0 cross-domain bridges
    "used_by_agent":        "Entity → Agent（跨域桥接）",
}


def _make_urn(entity_type: str, entity_id: str) -> str:
    return f"urn:aiplat:{entity_type}:{entity_id}"


class TripleStore:
    """统一跨图三元组存储。"""

    def __init__(self, db_path: str = ""):
        # AIPLAT_HOME 优先（配置驱动，§5；复用 core.utils.paths 权威路径解析，防路径漂移）
        from core.utils.paths import get_aiplat_home
        path = db_path or os.path.join(get_aiplat_home(), "ontology_triples.sqlite3")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS triples (
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'code_scan',
                metadata TEXT DEFAULT '{}',
                PRIMARY KEY (subject, predicate, object)
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_subject ON triples(subject)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_object ON triples(object)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_predicate ON triples(predicate)")
        self._conn.commit()

    def add(self, subject: str, predicate: str, object: str,
            confidence: float = 1.0, source: str = "code_scan",
            metadata: dict = None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO triples VALUES (?, ?, ?, ?, ?, ?)",
            (subject, predicate, object, confidence, source,
             json.dumps(metadata or {}, ensure_ascii=False)))
        self._conn.commit()

    def add_batch(self, triples: List[Tuple[str, str, str, float, str, dict]]) -> None:
        """批量写入三元组。自动序列化 metadata dict。"""
        serialized = [
            (s, p, o, c, src, json.dumps(m, ensure_ascii=False) if isinstance(m, dict) else m or "{}")
            for s, p, o, c, src, m in triples
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO triples VALUES (?, ?, ?, ?, ?, ?)", serialized)
        self._conn.commit()

    def clear_source(self, source: str = "code_scan") -> int:
        c = self._conn.execute("DELETE FROM triples WHERE source = ?", (source,))
        self._conn.commit()
        return c.rowcount

    # ── Core queries ──────────────────────────────

    def get_downstream(self, urn: str, depth: int = 3) -> List[Dict[str, Any]]:
        """BFS 多跳下游遍历。"""
        results: List[Dict[str, Any]] = []
        visited = {urn}
        queue = [(urn, 0, [urn])]
        while queue:
            current, d, chain = queue.pop(0)
            if d >= depth:
                continue
            rows = self._conn.execute(
                "SELECT subject, predicate, object, confidence FROM triples WHERE subject = ?",
                (current,)).fetchall()
            for row in rows:
                obj = row[2]
                edge = {"subject": row[0], "predicate": row[1], "object": obj,
                        "confidence": row[3], "depth": d + 1,
                        "chain": chain + [f"{row[1]}→{obj}"]}
                results.append(edge)
                if obj not in visited:
                    visited.add(obj)
                    queue.append((obj, d + 1, chain + [obj]))
        return results

    def get_upstream(self, urn: str, depth: int = 3) -> List[Dict[str, Any]]:
        """BFS 反向多跳遍历（哪些实体依赖了我）。"""
        results: List[Dict[str, Any]] = []
        visited = {urn}
        queue = [(urn, 0, [urn])]
        while queue:
            current, d, chain = queue.pop(0)
            if d >= depth:
                continue
            rows = self._conn.execute(
                "SELECT subject, predicate, object, confidence FROM triples WHERE object = ?",
                (current,)).fetchall()
            for row in rows:
                subj = row[0]
                edge = {"subject": subj, "predicate": row[1], "object": current,
                        "confidence": row[3], "depth": d + 1,
                        "chain": [subj] + chain}
                results.append(edge)
                if subj not in visited:
                    visited.add(subj)
                    queue.append((subj, d + 1, [subj] + chain))
        return results

    def get_by_predicate(self, predicate: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT subject, predicate, object, confidence FROM triples WHERE predicate = ?",
            (predicate,)).fetchall()
        return [{"subject": r[0], "predicate": r[1], "object": r[2], "confidence": r[3]}
                for r in rows]

    def stats(self) -> Dict[str, Any]:
        total = self._conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
        preds = self._conn.execute(
            "SELECT predicate, COUNT(*) as cnt FROM triples GROUP BY predicate"
        ).fetchall()
        return {
            "total_triples": total,
            "by_predicate": [{"predicate": r[0], "count": r[1]} for r in preds],
        }


_store: Optional[TripleStore] = None


def get_triple_store() -> TripleStore:
    global _store
    if _store is None:
        _store = TripleStore()
    return _store


# ── CLI entry ────────────────────────────────────

if __name__ == "__main__":
    import sys
    store = get_triple_store()
    urn = sys.argv[1] if len(sys.argv) > 1 else ""
    if not urn:
        # Show stats if no URN given
        s = store.stats()
        print(f"Total triples: {s['total_triples']}")
        for p in s["by_predicate"]:
            label = TRIPLE_TYPES.get(p["predicate"], p["predicate"])
            print(f"  {p['predicate']} ({label}): {p['count']}")
    else:
        print(f"=== Downstream of {urn} ===")
        for r in store.get_downstream(urn, depth=3):
            pfx = "──" * r["depth"]
            print(f"  {pfx}{r['predicate']} → {r['object']}")
        print(f"\n=== Upstream of {urn} ===")
        for r in store.get_upstream(urn, depth=3):
            pfx = "──" * r["depth"]
            print(f"  {pfx}{r['subject']} → {r['predicate']}")
