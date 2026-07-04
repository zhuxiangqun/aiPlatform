"""Wiki Quality Monitor — content fidelity vs original source documents.

Checks whether Wiki page body accurately reflects its `source_articles` original
documents. This is the ONE dimension missing from wiki_health_rules.py (which
covers structural/lint/relation health only).

Architecture:
  1. Sample N wiki pages with non-empty source_articles
  2. Fetch original document content from kb_elements table
  3. LLM evaluates completeness, accuracy, overall score (0-100)
  4. Store in wiki_quality_alerts + wiki_quality_trends tables
  5. Expose via diagnostics API + HealthCheckRegistry

Trigger modes:
  - On-demand: GET /diagnostics/wiki-quality?force=true
  - Event-driven: after ≥50 wiki page mutations (via wiki_engine hook)
  - Cron: daily at 3 AM (controlled by _cron_hour)
"""

from __future__ import annotations

import json
import logging
import os
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.wiki_quality")


@dataclass
class WikiQualityScore:
    page_title: str
    collection_id: str
    source_count: int
    completeness: float   # 0-100
    accuracy: float       # 0-100
    overall: float        # 0-100
    explanation: str = ""
    checked_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_title": self.page_title,
            "collection_id": self.collection_id,
            "source_count": self.source_count,
            "completeness": round(self.completeness, 1),
            "accuracy": round(self.accuracy, 1),
            "overall": round(self.overall, 1),
            "explanation": self.explanation,
            "checked_at": self.checked_at,
        }


# ═══════════════════════════════════════════════════════════════
# Database
# ═══════════════════════════════════════════════════════════════

_DB_PATH = os.path.expanduser(
    os.getenv("AIPLAT_WIKI_QUALITY_DB", "~/.aiplat/wiki_quality.sqlite3")
)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS wiki_quality_alerts (
            page_title TEXT NOT NULL,
            collection_id TEXT DEFAULT 'default',
            source_count INTEGER DEFAULT 0,
            completeness REAL DEFAULT 0,
            accuracy REAL DEFAULT 0,
            overall REAL DEFAULT 0,
            explanation TEXT DEFAULT '',
            checked_at TEXT NOT NULL,
            reviewed INTEGER DEFAULT 0,
            PRIMARY KEY (page_title, collection_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS wiki_quality_trends (
            page_title TEXT NOT NULL,
            collection_id TEXT DEFAULT 'default',
            checked_at TEXT NOT NULL,
            completeness REAL DEFAULT 0,
            accuracy REAL DEFAULT 0,
            overall REAL DEFAULT 0,
            PRIMARY KEY (page_title, collection_id, checked_at)
        )"""
    )
    conn.commit()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


# ═══════════════════════════════════════════════════════════════
# Source document fetching
# ═══════════════════════════════════════════════════════════════

def _fetch_source_content(source_refs: List[str], tenant_id: str = "default") -> str:
    """Fetch raw content for kb: source references from kb_elements.

    Uses 3-segment sampling: if total text > 3000 chars, takes 3 segments
    (front/middle/back, 1000 chars each) for even coverage.
    """
    kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    kb_db = os.path.join(kb_dir, tenant_id, "kb.sqlite3")
    if not os.path.exists(kb_db):
        return ""

    conn = sqlite3.connect(kb_db)
    conn.row_factory = sqlite3.Row
    try:
        all_texts: List[str] = []
        for ref in source_refs:
            if not ref or not isinstance(ref, str) or not ref.startswith("kb:"):
                continue
            doc_id = ref[3:]  # strip "kb:" prefix
            rows = conn.execute(
                "SELECT text FROM kb_elements WHERE tenant_id=? AND doc_id=? AND type='text' ORDER BY page_idx, created_at",
                (tenant_id, doc_id),
            ).fetchall()
            for r in rows:
                t = (r["text"] or "").strip()
                if t:
                    all_texts.append(t)

        full_text = "\n\n".join(all_texts)
        if len(full_text) <= 3000:
            return full_text

        # 3-segment sampling
        seg_len = len(full_text) // 3
        parts = [
            full_text[:1000],
            full_text[seg_len : seg_len + 1000],
            full_text[-1000:],
        ]
        return f"[片段1 (前1/3)]\n{parts[0]}\n\n---\n\n[片段2 (中1/3)]\n{parts[1]}\n\n---\n\n[片段3 (后1/3)]\n{parts[2]}"
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# LLM evaluation
# ═══════════════════════════════════════════════════════════════

_QUALITY_PROMPT = """你是文档质量评估专家。请对比以下 Wiki 页面内容与原始文档片段，评估 Wiki 页面的信息完整性、准确性和整体质量。

## Wiki 页面内容
{wiki_body}

## 原始文档片段（来源）
{source_content}

请以 JSON 格式返回评估结果（只返回 JSON，不要其他文字）:
{{
  "completeness": 0-100,
  "completeness_reason": "一句话说明信息保留情况",
  "accuracy": 0-100,
  "accuracy_reason": "一句话说明是否有与原文矛盾之处",
  "overall": 0-100,
  "explanation": "综合评估（1-2句）"
}}

评分标准:
- completeness: 原始文档的关键信息在 Wiki 页面中保留了多少？90+几乎完整, 70-89大部分保留, 50-69部分丢失, <50严重丢失
- accuracy: Wiki 页面是否有与原文矛盾的陈述？100完全一致, 90-99微小差异, 70-89有轻微偏差, <70有实质性矛盾
- overall: 综合评价，completeness * 0.6 + accuracy * 0.4 的加权结果"""


async def _evaluate_page(question: str, wiki_body: str, source_content: str) -> WikiQualityScore:
    """Use LLM to evaluate Wiki page content quality against source documents."""
    if not source_content or not wiki_body:
        return WikiQualityScore(
            page_title=question, collection_id="default",
            source_count=0, completeness=0, accuracy=0, overall=0,
            explanation="无源文档可供对比" if not source_content else "Wiki 页面内容为空",
        )

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose

        prompt = _QUALITY_PROMPT.format(
            wiki_body=wiki_body[:3000],
            source_content=source_content,
        )
        resp = await sys_llm_generate(
            None,
            [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("doc_llm"),
            temperature=0,
            max_tokens=500,
        )
        text = getattr(resp, "content", "") or str(resp)

        # Parse JSON from LLM output
        parsed = _parse_eval_response(text)
        return WikiQualityScore(
            page_title=question, collection_id="default",
            source_count=1,
            completeness=parsed.get("completeness", 0),
            accuracy=parsed.get("accuracy", 0),
            overall=parsed.get("overall", 0),
            explanation=parsed.get("explanation", ""),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.debug("LLM evaluation failed for '%s': %s", question, e)
        return WikiQualityScore(
            page_title=question, collection_id="default",
            source_count=1, completeness=0, accuracy=0, overall=0,
            explanation=f"评估失败: {str(e)[:100]}",
        )


def _parse_eval_response(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM evaluation response."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    import re
    m = re.search(r"\{[\s\S]*\"completeness\"[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


# ═══════════════════════════════════════════════════════════════
# Main monitor class
# ═══════════════════════════════════════════════════════════════

class WikiQualityMonitor:
    """Monitor Wiki page content quality against original source documents."""

    def __init__(self):
        self._cron_hour = int(os.getenv("AIPLAT_WIKI_QUALITY_CRON_HOUR", "3"))
        self._sample_size = int(os.getenv("AIPLAT_WIKI_QUALITY_SAMPLE_SIZE", "10"))
        self._running = False
        self._last_run: Optional[str] = None

    # ── Sampling ───────────────────────────────────────────

    def _sample_pages(self, collection_id: str = "default") -> List[Tuple[str, str, List[str]]]:
        """Sample pages with non-empty source_articles.

        Returns list of (title, body, source_articles).
        """
        try:
            from core.harness.knowledge.wiki_engine import list_all_pages, read_page

            all_pages = list_all_pages(collection_id=collection_id)
            candidates = []
            for p in all_pages:
                sources = p.get("source_articles") or []
                if sources:
                    candidates.append(p)
            if not candidates:
                return []

            # Prefer recently updated, take up to sample_size
            candidates.sort(
                key=lambda p: p.get("last_updated", ""), reverse=True
            )
            sampled = candidates[:self._sample_size]
            if len(sampled) < self._sample_size:
                # Fill with random from remaining
                from random import sample as rand_sample
                remaining = [p for p in candidates if p not in sampled]
                if remaining:
                    extra = rand_sample(remaining, min(self._sample_size - len(sampled), len(remaining)))
                    sampled.extend(extra)

            results = []
            for p in sampled:
                title = str(p.get("title", ""))
                if not title:
                    continue
                full = read_page(title, collection_id=collection_id)
                if full:
                    body = str(full.get("body", "") or "")
                    sources = full.get("source_articles") or p.get("source_articles") or []
                    results.append((title, body, list(sources)))
            return results
        except Exception as e:
            logger.debug("Page sampling failed: %s", e)
            return []

    # ── Quality check (entry point) ────────────────────────

    async def run_quality_check(
        self,
        *,
        collection_id: str = "default",
        force: bool = False,
    ) -> List[WikiQualityScore]:
        """Run a full quality check cycle. Pass force=True to skip cooldown."""
        if self._running:
            return []
        if not force and self._last_run:
            try:
                last_ts = datetime.fromisoformat(self._last_run.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
                if elapsed < 3600:  # 1-hour cooldown
                    return []
            except Exception:
                pass

        self._running = True
        try:
            samples = self._sample_pages(collection_id)
            if not samples:
                return []

            tenant_id = collection_id if collection_id != "default" else "default"
            scores: List[WikiQualityScore] = []
            for title, body, sources in samples:
                source_content = _fetch_source_content(sources, tenant_id=tenant_id)
                score = await _evaluate_page(title, body, source_content)
                scores.append(score)

            self._persist_scores(scores)
            self._last_run = datetime.now(timezone.utc).isoformat()
            return scores
        except Exception as e:
            logger.warning("Quality check failed: %s", e)
            return []
        finally:
            self._running = False

    # ── Persistence ────────────────────────────────────────

    def _persist_scores(self, scores: List[WikiQualityScore]) -> None:
        conn = _get_conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            for s in scores:
                if not s.page_title:
                    continue
                # Upsert alerts
                conn.execute(
                    """INSERT OR REPLACE INTO wiki_quality_alerts
                       (page_title, collection_id, source_count, completeness, accuracy, overall, explanation, checked_at, reviewed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (s.page_title, s.collection_id, s.source_count,
                     s.completeness, s.accuracy, s.overall, s.explanation, now),
                )
                # Append trend
                conn.execute(
                    """INSERT OR REPLACE INTO wiki_quality_trends
                       (page_title, collection_id, checked_at, completeness, accuracy, overall)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (s.page_title, s.collection_id, now,
                     s.completeness, s.accuracy, s.overall),
                )
            conn.commit()
        except Exception as e:
            logger.debug("Persist scores failed: %s", e)
        finally:
            conn.close()

    # ── Query API ──────────────────────────────────────────

    def get_alerts(self, *, limit: int = 20, collection_id: str = "default") -> List[Dict[str, Any]]:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM wiki_quality_alerts
                   WHERE collection_id=? AND reviewed=0
                   ORDER BY overall ASC LIMIT ?""",
                (collection_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_trends(self, *, page_title: str = "", collection_id: str = "default", limit: int = 10) -> List[Dict[str, Any]]:
        conn = _get_conn()
        try:
            if page_title:
                rows = conn.execute(
                    """SELECT * FROM wiki_quality_trends
                       WHERE page_title=? AND collection_id=?
                       ORDER BY checked_at DESC LIMIT ?""",
                    (page_title, collection_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM wiki_quality_trends
                       WHERE collection_id=?
                       ORDER BY checked_at DESC LIMIT ?""",
                    (collection_id, limit),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        conn = _get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) as n FROM wiki_quality_alerts").fetchone()
            avg = conn.execute(
                "SELECT AVG(overall) as avg_o, AVG(completeness) as avg_c, AVG(accuracy) as avg_a FROM wiki_quality_alerts"
            ).fetchone()
            low = conn.execute(
                "SELECT COUNT(*) as n FROM wiki_quality_alerts WHERE overall < 50 AND reviewed=0"
            ).fetchone()
            return {
                "total_checked": total["n"] if total else 0,
                "avg_overall": round(avg["avg_o"] or 0, 1) if avg else 0,
                "avg_completeness": round(avg["avg_c"] or 0, 1) if avg else 0,
                "avg_accuracy": round(avg["avg_a"] or 0, 1) if avg else 0,
                "low_quality_unreviewed": low["n"] if low else 0,
                "last_run": self._last_run,
            }
        finally:
            conn.close()

    def mark_reviewed(self, page_title: str, collection_id: str = "default") -> None:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE wiki_quality_alerts SET reviewed=1 WHERE page_title=? AND collection_id=?",
                (page_title, collection_id),
            )
            conn.commit()
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════════
# Singleton + trigger
# ═══════════════════════════════════════════════════════════════

_monitor: Optional[WikiQualityMonitor] = None
_enabled = os.getenv("AIPLAT_WIKI_QUALITY_ENABLED", "true").lower() in ("1", "true", "yes", "y")


def get_wiki_quality_monitor() -> WikiQualityMonitor:
    global _monitor
    if _monitor is None:
        _monitor = WikiQualityMonitor()
    return _monitor


def trigger_quality_check() -> None:
    """Non-blocking quality check trigger (called from wiki_engine hook)."""
    if not _enabled:
        return
    import asyncio
    try:
        monitor = get_wiki_quality_monitor()
        asyncio.create_task(monitor.run_quality_check())
    except Exception as e:
        logger.debug("Trigger quality check failed: %s", e)
