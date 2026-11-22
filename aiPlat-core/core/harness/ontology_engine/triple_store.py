"""
OntologyTripleStore — unified cross-graph triple storage and query engine.

Bridges the 5 isolated graphs (GraphIndex, CapabilityGraph, CodeGraph, Wiki, KB)
via a single (subject, predicate, object) triple store backed by SQLite.

Supports BFS multi-hop traversal for cross-domain impact analysis.

N19 / SECURITY V2：``tenant_id`` 列 + 查询过滤（显式 tenant 只见本租户+共享空串行）。

Usage:
    store = get_triple_store()
    store.add("urn:aiplat:agent:rag_agent", "uses_skill", "urn:aiplat:skill:knowledge_retrieve")
    impact = store.get_downstream("urn:aiplat:agent:rag_agent", depth=3, tenant_id="t1")
    sources = store.get_upstream("urn:aiplat:skill:knowledge_retrieve", depth=3, tenant_id="t1")

CLI:
    python -m core.harness.ontology_engine.triple_store urn:aiplat:agent:rag_agent
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

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
    """统一跨图三元组存储（可选按 tenant 过滤读路径）。"""

    def __init__(self, db_path: str = ""):
        # AIPLAT_HOME 优先（配置驱动，§5；复用 core.utils.paths 权威路径解析，防路径漂移）
        """初始化。

        Args:
            db_path: db_path 参数。
        """
        from core.utils.paths import get_aiplat_home
        path = db_path or os.path.join(get_aiplat_home(), "ontology_triples.sqlite3")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._ensure_schema()
        self._conn.commit()

    def _ensure_schema(self) -> None:
        """确保 triples 表含 tenant_id，并完成旧库迁移。"""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS triples (
                tenant_id TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'code_scan',
                metadata TEXT DEFAULT '{}',
                PRIMARY KEY (tenant_id, subject, predicate, object)
            )
            """
        )
        cols = {
            str(r[1])
            for r in self._conn.execute("PRAGMA table_info(triples)").fetchall()
        }
        if "tenant_id" not in cols:
            # 为什么：旧库无 tenant_id；重建表保留 SPO，共享行 tenant_id=''
            _log.info("TripleStore migrating triples table to add tenant_id")
            self._conn.execute(
                """
                CREATE TABLE triples_v2 (
                    tenant_id TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'code_scan',
                    metadata TEXT DEFAULT '{}',
                    PRIMARY KEY (tenant_id, subject, predicate, object)
                )
                """
            )
            self._conn.execute(
                """
                INSERT OR IGNORE INTO triples_v2
                    (tenant_id, subject, predicate, object, confidence, source, metadata)
                SELECT '', subject, predicate, object, confidence, source, metadata
                FROM triples
                """
            )
            self._conn.execute("DROP TABLE triples")
            self._conn.execute("ALTER TABLE triples_v2 RENAME TO triples")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_triples_tenant ON triples(tenant_id)"
        )

    @staticmethod
    def _tenant_clause(tenant_id: str) -> Tuple[str, Tuple[Any, ...]]:
        """显式 tenant：本租户 + 共享空串；空 tenant：全量（兼容旧调用）。

        Args:
            tenant_id: 租户；空则不加过滤。
        """
        tid = (tenant_id or "").strip()
        if not tid:
            return "", ()
        # 为什么：共享平台三元组（tenant_id=''）对所有租户可见；禁跨租户行
        return " AND (tenant_id = ? OR tenant_id = '')", (tid,)

    def add(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 1.0,
        source: str = "code_scan",
        metadata: dict = None,
        *,
        tenant_id: str = "",
    ) -> None:
        """add。

        Args:
            subject: subject 参数。
            predicate: predicate 参数。
            object: object 参数。
            confidence: confidence 参数。
            source: source 参数。
            metadata: metadata 参数。
            tenant_id: 租户；空串表示平台共享。
        """
        tid = (tenant_id or "").strip()
        self._conn.execute(
            "INSERT OR REPLACE INTO triples "
            "(tenant_id, subject, predicate, object, confidence, source, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                subject,
                predicate,
                object,
                confidence,
                source,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def add_batch(
        self,
        triples: List[Tuple[Any, ...]],
        *,
        tenant_id: str = "",
    ) -> None:
        """批量写入三元组。自动序列化 metadata dict。

        Args:
            triples: 6 元组 ``(s,p,o,c,src,meta)`` 或 7 元组含领先 ``tenant_id``。
            tenant_id: 默认租户（6 元组时使用）。
        """
        default_tid = (tenant_id or "").strip()
        serialized = []
        for row in triples:
            if len(row) == 7:
                tid, s, p, o, c, src, m = row
            else:
                s, p, o, c, src, m = row
                tid = default_tid
            serialized.append(
                (
                    (tid or "").strip(),
                    s,
                    p,
                    o,
                    c,
                    src,
                    json.dumps(m, ensure_ascii=False) if isinstance(m, dict) else m or "{}",
                )
            )
        self._conn.executemany(
            "INSERT OR REPLACE INTO triples "
            "(tenant_id, subject, predicate, object, confidence, source, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            serialized,
        )
        self._conn.commit()

    def clear_source(self, source: str = "code_scan", *, tenant_id: str = "") -> int:
        """clear_source。

        Args:
            source: source 参数。
            tenant_id: 非空时只清该租户（不含共享行）。
        """
        tid = (tenant_id or "").strip()
        if tid:
            c = self._conn.execute(
                "DELETE FROM triples WHERE source = ? AND tenant_id = ?",
                (source, tid),
            )
        else:
            c = self._conn.execute("DELETE FROM triples WHERE source = ?", (source,))
        self._conn.commit()
        return c.rowcount

    # ── Core queries ──────────────────────────────

    def get_downstream(
        self, urn: str, depth: int = 3, *, tenant_id: str = ""
    ) -> List[Dict[str, Any]]:
        """BFS 多跳下游遍历。

        Args:
            urn: urn 参数。
            depth: depth 参数。
            tenant_id: 非空时按租户+共享过滤。
        """
        results: List[Dict[str, Any]] = []
        visited = {urn}
        queue = [(urn, 0, [urn])]
        clause, tparams = self._tenant_clause(tenant_id)
        while queue:
            current, d, chain = queue.pop(0)
            if d >= depth:
                continue
            rows = self._conn.execute(
                "SELECT subject, predicate, object, confidence FROM triples "
                f"WHERE subject = ?{clause}",
                (current, *tparams),
            ).fetchall()
            for row in rows:
                obj = row[2]
                edge = {
                    "subject": row[0],
                    "predicate": row[1],
                    "object": obj,
                    "confidence": row[3],
                    "depth": d + 1,
                    "chain": chain + [f"{row[1]}→{obj}"],
                }
                results.append(edge)
                if obj not in visited:
                    visited.add(obj)
                    queue.append((obj, d + 1, chain + [obj]))
        return results

    def get_upstream(
        self, urn: str, depth: int = 3, *, tenant_id: str = ""
    ) -> List[Dict[str, Any]]:
        """BFS 反向多跳遍历（哪些实体依赖了我）。

        Args:
            urn: urn 参数。
            depth: depth 参数。
            tenant_id: 非空时按租户+共享过滤。
        """
        results: List[Dict[str, Any]] = []
        visited = {urn}
        queue = [(urn, 0, [urn])]
        clause, tparams = self._tenant_clause(tenant_id)
        while queue:
            current, d, chain = queue.pop(0)
            if d >= depth:
                continue
            rows = self._conn.execute(
                "SELECT subject, predicate, object, confidence FROM triples "
                f"WHERE object = ?{clause}",
                (current, *tparams),
            ).fetchall()
            for row in rows:
                subj = row[0]
                edge = {
                    "subject": subj,
                    "predicate": row[1],
                    "object": current,
                    "confidence": row[3],
                    "depth": d + 1,
                    "chain": [subj] + chain,
                }
                results.append(edge)
                if subj not in visited:
                    visited.add(subj)
                    queue.append((subj, d + 1, [subj] + chain))
        return results

    def get_by_predicate(
        self, predicate: str, *, tenant_id: str = ""
    ) -> List[Dict[str, Any]]:
        """获取 by_predicate。

        Args:
            predicate: predicate 参数。
            tenant_id: 非空时按租户+共享过滤。
        """
        clause, tparams = self._tenant_clause(tenant_id)
        rows = self._conn.execute(
            "SELECT subject, predicate, object, confidence FROM triples "
            f"WHERE predicate = ?{clause}",
            (predicate, *tparams),
        ).fetchall()
        return [
            {
                "subject": r[0],
                "predicate": r[1],
                "object": r[2],
                "confidence": r[3],
            }
            for r in rows
        ]

    def stats(self, *, tenant_id: str = "") -> Dict[str, Any]:
        """stats。

        Args:
            tenant_id: 非空时按租户+共享过滤。
        """
        clause, tparams = self._tenant_clause(tenant_id)
        where = f"WHERE 1=1{clause}" if clause else ""
        total = self._conn.execute(
            f"SELECT COUNT(*) FROM triples {where}", tparams
        ).fetchone()[0]
        preds = self._conn.execute(
            f"SELECT predicate, COUNT(*) as cnt FROM triples {where} "
            "GROUP BY predicate",
            tparams,
        ).fetchall()
        return {
            "total_triples": total,
            "by_predicate": [{"predicate": r[0], "count": r[1]} for r in preds],
            "tenant_scoped": bool((tenant_id or "").strip()),
        }


_store: Optional[TripleStore] = None


def get_triple_store() -> TripleStore:
    """获取 triple_store。
    """
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
