"""
KnowledgeROI — 知识编译 ROI 追踪 (Karpathy LLM Wiki 对齐)

追踪每次查询的 Token 消耗对比:
  - RAG 模式: 需要多少次检索 + Token 消耗
  - Wiki 预编译模式: 直接从 GraphIndex 结构化查询的 Token 消耗
  - 累积节省: 滚动求和 saved_tokens + 折合成本

表: knowledge_roi (schema v54)

调用者: CompilationDashboard 前端 / REST API GET /knowledge/roi
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import sqlite3 as _sqlite3
import time as _time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROI_DB_PATH = _os.path.expanduser(
    _os.getenv("AIPLAT_ROI_DB_PATH", "~/.aiplat/data/aiplat_platform.sqlite3")
)


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class ROIEntry:
    """单次查询的 ROI 记录."""
    query_id: str
    domain_id: str
    query_text: str = ""                    # 查询文本 (截断到200字符)
    rag_tokens: int = 0                     # RAG 模式 Token 消耗
    wiki_tokens: int = 0                    # Wiki 预编译模式 Token 消耗
    saved_tokens: int = 0                   # 节省 Token
    saved_percent: float = 0.0              # 节省百分比
    query_time: float = 0.0                 # 查询时间戳
    cache_hit: bool = False                 # 是否命中 SemanticCache

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "domain_id": self.domain_id,
            "query_text": self.query_text[:200],
            "rag_tokens": self.rag_tokens,
            "wiki_tokens": self.wiki_tokens,
            "saved_tokens": self.saved_tokens,
            "saved_percent": round(self.saved_percent, 1),
            "query_time": self.query_time,
            "cache_hit": self.cache_hit,
        }


@dataclass
class ROISummary:
    """ROI 汇总."""
    total_queries: int
    total_rag_tokens: int
    total_wiki_tokens: int
    total_saved_tokens: int
    avg_saved_percent: float
    estimated_cost_saved: float            # 折合成本 (元) — 按 DeepSeek 价格估算
    by_domain: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    trend: List[Dict[str, Any]] = field(default_factory=list)  # 时间趋势


# ── KnowledgeROI ─────────────────────────────────────────────────────────

class KnowledgeROI:
    """知识 ROI 追踪器.

    使用方式:
        roi = KnowledgeROI()
        roi.record(query_id, "ai-knowledge", rag_tokens=5000, wiki_tokens=500, cache_hit=True)
        summary = roi.summary(domain_id="ai-knowledge", days=30)
    """

    def _ensure_schema(self, conn: _sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_roi (
                query_id TEXT PRIMARY KEY,
                domain_id TEXT NOT NULL,
                query_text TEXT DEFAULT '',
                rag_tokens INTEGER NOT NULL DEFAULT 0,
                wiki_tokens INTEGER NOT NULL DEFAULT 0,
                saved_tokens INTEGER NOT NULL DEFAULT 0,
                saved_percent REAL NOT NULL DEFAULT 0.0,
                query_time REAL NOT NULL,
                cache_hit INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_roi_domain_time ON knowledge_roi(domain_id, query_time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_roi_time ON knowledge_roi(query_time)")
        conn.commit()

    def _get_conn(self) -> _sqlite3.Connection:
        conn = _sqlite3.connect(ROI_DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = _sqlite3.Row
        return conn

    def record(
        self,
        query_id: str,
        domain_id: str,
        *,
        query_text: str = "",
        rag_tokens: int = 0,
        wiki_tokens: int = 0,
        cache_hit: bool = False,
    ) -> str:
        """记录一次查询的 ROI 数据."""
        saved = max(0, rag_tokens - wiki_tokens)
        saved_pct = (saved / max(rag_tokens, 1)) * 100

        try:
            conn = self._get_conn()
            self._ensure_schema(conn)
            conn.execute(
                """INSERT OR REPLACE INTO knowledge_roi
                   (query_id, domain_id, query_text, rag_tokens, wiki_tokens, saved_tokens, saved_percent, query_time, cache_hit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_id, domain_id, query_text[:200], rag_tokens, wiki_tokens, saved, round(saved_pct, 1), _time.time(), 1 if cache_hit else 0),
            )
            conn.commit()
            conn.close()
            logger.debug("ROI recorded: %s saved %d tokens (%.1f%%)", query_id, saved, saved_pct)
            return query_id
        except Exception as e:
            logger.warning("ROI record failed: %s", e)
            return ""

    def record_from_syscall(
        self,
        query_text: str,
        domain_id: str,
        rag_tokens: int,
        wiki_tokens: int,
        cache_hit: bool = False,
    ) -> str:
        """从 syscall 层快速记录 (自动生成 query_id)."""
        qid = f"q_{_uuid.uuid4().hex[:12]}"
        return self.record(qid, domain_id, query_text=query_text[:200], rag_tokens=rag_tokens, wiki_tokens=wiki_tokens, cache_hit=cache_hit)

    def summary(
        self,
        *,
        domain_id: str = "",
        days: int = 30,
    ) -> ROISummary:
        """获取 ROI 汇总.

        Args:
            domain_id: 域ID (为空则全量)
            days: 统计天数

        Returns:
            ROISummary
        """
        cutoff = _time.time() - days * 86400
        domain_filter = "AND domain_id = ?" if domain_id else ""
        params: tuple = (domain_id, cutoff, cutoff) if domain_id else (cutoff, cutoff)

        try:
            conn = self._get_conn()
            self._ensure_schema(conn)

            # 汇总统计
            row = conn.execute(
                f"""SELECT COUNT(*) as total_queries,
                           COALESCE(SUM(rag_tokens), 0) as total_rag,
                           COALESCE(SUM(wiki_tokens), 0) as total_wiki,
                           COALESCE(SUM(saved_tokens), 0) as total_saved,
                           COALESCE(AVG(saved_percent), 0) as avg_pct
                    FROM knowledge_roi
                    WHERE query_time > ? {domain_filter}""",
                params,
            ).fetchone()

            total_queries = row[0] if row else 0
            total_rag = row[1] if row else 0
            total_wiki = row[2] if row else 0
            total_saved = row[3] if row else 0
            avg_pct = row[4] if row else 0

            # 按域聚合
            by_domain: Dict[str, Dict[str, Any]] = {}
            domain_rows = conn.execute(
                """SELECT domain_id, COUNT(*) as cnt, SUM(saved_tokens) as saved, AVG(saved_percent) as pct
                   FROM knowledge_roi WHERE query_time > ? GROUP BY domain_id""",
                (cutoff,),
            ).fetchall()
            for dr in domain_rows:
                by_domain[dr["domain_id"]] = {
                    "queries": dr["cnt"],
                    "saved_tokens": dr["saved"] or 0,
                    "avg_saved_pct": round(dr["pct"] or 0, 1),
                }

            # 时间趋势 (按日聚合)
            trend_rows = conn.execute(
                f"""SELECT DATE(query_time, 'unixepoch') as day,
                           COUNT(*) as cnt, SUM(saved_tokens) as saved
                    FROM knowledge_roi
                    WHERE query_time > ? {domain_filter}
                    GROUP BY day ORDER BY day""",
                params,
            ).fetchall()
            trend = [{"day": r["day"], "queries": r["cnt"], "saved_tokens": r["saved"] or 0} for r in trend_rows]

            conn.close()

            # 成本估算 (DeepSeek 价格: ¥1/百万Token)
            cost_per_million = 1.0
            estimated_cost = (total_saved / 1_000_000) * cost_per_million

            return ROISummary(
                total_queries=total_queries,
                total_rag_tokens=total_rag,
                total_wiki_tokens=total_wiki,
                total_saved_tokens=total_saved,
                avg_saved_percent=round(avg_pct, 1),
                estimated_cost_saved=round(estimated_cost, 2),
                by_domain=by_domain,
                trend=trend,
            )

        except Exception as e:
            logger.warning("ROI summary failed: %s", e)
            return ROISummary(total_queries=0, total_rag_tokens=0, total_wiki_tokens=0, total_saved_tokens=0, avg_saved_percent=0.0, estimated_cost_saved=0.0)

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的 ROI 记录."""
        try:
            conn = self._get_conn()
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT * FROM knowledge_roi ORDER BY query_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []
