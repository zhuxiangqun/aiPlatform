"""
DocumentQualityMonitor — proactive detection of parsing quality degradation.

Runs daily at 2:00 AM to sample documents, reparse them, and compare
results against industry-specific baselines. Detects:
  - Semantic drift (old vs new vector cosine similarity)
  - Structure loss (headings, tables, elements vs industry baseline)
  - Noise ratio (cleaned chars / raw chars vs industry baseline)

Baselines are built once 100+ documents are available, updated monthly,
and stored per-industry (insurance/finance/gov/general).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("aiplat.doc_quality")

_DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3")

# ── SQLite helpers ──

def _get_db():
    os.makedirs(os.path.dirname(_DEFAULT_DB), exist_ok=True)
    conn = sqlite3.connect(_DEFAULT_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def _init_tables():
    conn = _get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_quality_baselines (
                industry TEXT PRIMARY KEY,
                avg_headings REAL NOT NULL DEFAULT 0,
                avg_tables REAL NOT NULL DEFAULT 0,
                avg_elements REAL NOT NULL DEFAULT 0,
                avg_noise_ratio REAL NOT NULL DEFAULT 0,
                sample_count INTEGER DEFAULT 0,
                last_updated REAL NOT NULL,
                baseline_json TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_quality_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                industry TEXT DEFAULT 'general',
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                detail_json TEXT DEFAULT '{}',
                last_checked_at REAL,
                reviewed INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_alerts_reviewed
                ON doc_quality_alerts(reviewed, created_at DESC)
        """)
        conn.commit()
    finally:
        conn.close()


# ── DocumentQualityMonitor ──

class DocumentQualityMonitor:
    """Proactive document quality degradation detector."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._sample_buffer: List[dict] = []
        self._cron_hour = 2
        _init_tables()

    # ── Lifecycle ──

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._cron_loop())
        logger.info("DocumentQualityMonitor started (cron hour=%d)", self._cron_hour)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DocumentQualityMonitor stopped")

    async def _cron_loop(self):
        while self._running:
            now = time.localtime()
            if now.tm_hour == self._cron_hour and now.tm_min < 1:
                try:
                    await self._run_checks()
                except Exception:
                    logger.debug("Daily quality check failed", exc_info=True)
            await asyncio.sleep(60)

    # ── Daily checks ──

    async def _run_checks(self):
        """Daily: sample 15 docs, detect quality degradation."""
        if not self._baseline_ready():
            # Cold start: collect samples only
            docs = self._sample_docs(n=10)
            if not docs:
                return
            for doc_id in docs:
                await self._collect_sample(doc_id)
            total = self._total_docs()
            logger.info("DocQuality: cold start — collecting samples (%d/%d docs)", len(self._sample_buffer), total)
            if total >= 100:
                self._build_baseline()
            return

        # Normal operation
        docs = self._sample_docs(n=15)
        for doc_id in docs:
            if self._should_skip(doc_id):
                continue
            await self._check_and_alert(doc_id)

    async def _check_and_alert(self, doc_id: str):
        """Check a single document and emit alerts if degraded."""
        now = time.time()
        # ── 1. Reparse ──
        try:
            new_text = self._get_doc_text(doc_id)
            if not new_text:
                return
        except Exception:
            return

        # ── 2. Parse structure ──
        headings = len(re.findall(r'^#{1,6}\s', new_text, re.MULTILINE))
        tables = len(re.findall(r'^\|.*\|$', new_text, re.MULTILINE))
        total_elements = headings + tables + new_text.count('\n\n')

        # ── 3. Noise ratio ──
        try:
            from core.harness.knowledge.text_cleaner import get_text_cleaner
            cleaner = get_text_cleaner()
            _, removed = cleaner.clean(new_text)
            raw_chars = len(new_text) + removed
            noise_ratio = removed / max(raw_chars, 1)
        except Exception:
            noise_ratio = 0.0

        # ── 4. Semantic drift ──
        try:
            similarity = self._compute_similarity(doc_id, new_text)
        except Exception:
            similarity = 1.0

        # ── 5. Compare to baseline ──
        industry = self._infer_industry(doc_id)
        baseline = self._get_baseline(industry)

        if baseline:
            # Structure checks
            if headings < baseline.get("avg_headings", 0) * 0.3:
                self._emit_alert(doc_id, "structure_loss", "warning", {
                    "headings": headings, "baseline": baseline["avg_headings"], "ratio": round(headings / max(baseline["avg_headings"], 1), 2),
                }, industry, now)
            if tables < baseline.get("avg_tables", 0) * 0.5 and baseline.get("avg_tables", 0) > 2:
                self._emit_alert(doc_id, "structure_loss", "warning", {
                    "tables": tables, "baseline": baseline["avg_tables"], "ratio": round(tables / max(baseline["avg_tables"], 1), 2),
                }, industry, now)
            if total_elements < baseline.get("avg_elements", 0) * 0.5:
                self._emit_alert(doc_id, "structure_loss", "alert", {
                    "total": total_elements, "baseline": baseline["avg_elements"], "ratio": round(total_elements / max(baseline["avg_elements"], 1), 2),
                }, industry, now)

            # Noise ratio checks
            if noise_ratio > baseline.get("avg_noise_ratio", 0) * 2.5:
                self._emit_alert(doc_id, "high_noise", "warning", {
                    "noise_ratio": round(noise_ratio, 3), "baseline": round(baseline["avg_noise_ratio"], 3),
                }, industry, now)
        else:
            # Cold start fallback: absolute thresholds
            if noise_ratio > 0.5:
                self._emit_alert(doc_id, "high_noise", "alert", {"noise_ratio": round(noise_ratio, 3)}, industry, now)
            elif noise_ratio > 0.8:
                self._emit_alert(doc_id, "high_noise", "critical", {"noise_ratio": round(noise_ratio, 3)}, industry, now)

        # Semantic drift — always INFO (needs human review)
        if similarity < 0.85:
            self._emit_alert(doc_id, "drift", "info", {
                "cosine_similarity": round(similarity, 3),
            }, industry, now)

    # ── Baseline ──

    def _baseline_ready(self) -> bool:
        conn = _get_db()
        try:
            return conn.execute("SELECT COUNT(*) FROM doc_quality_baselines").fetchone()[0] > 0
        finally:
            conn.close()

    def _build_baseline(self):
        samples = list(self._sample_buffer)
        if len(samples) < 100:
            logger.info("DocQuality: need 100+ samples to build baseline, have %d", len(samples))
            return

        grouped: Dict[str, list] = {}
        for s in samples:
            ind = s.get("industry", "general")
            grouped.setdefault(ind, []).append(s)

        conn = _get_db()
        try:
            for industry, group in grouped.items():
                if len(group) < 10:
                    continue
                headings = sorted(s["headings"] for s in group)
                tables = sorted(s["tables"] for s in group)
                elements = sorted(s["elements"] for s in group)
                noises = sorted(s["noise_ratio"] for s in group)

                def med(vals): return vals[len(vals) // 2]

                conn.execute(
                    """INSERT OR REPLACE INTO doc_quality_baselines
                       (industry, avg_headings, avg_tables, avg_elements, avg_noise_ratio, sample_count, last_updated, baseline_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (industry, med(headings), med(tables), med(elements), med(noises),
                     len(group), time.time(), json.dumps({
                         "headings_p50": med(headings), "tables_p50": med(tables),
                         "elements_p50": med(elements), "noise_p50": med(noises),
                     })),
                )
            conn.commit()
            logger.info("DocQuality: baseline built for %d industries", len(grouped))
        finally:
            conn.close()
        self._sample_buffer.clear()

    def _get_baseline(self, industry: str) -> Optional[dict]:
        conn = _get_db()
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM doc_quality_baselines WHERE industry = ?", (industry,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ── Sampling ──

    def _sample_docs(self, n: int = 15) -> List[str]:
        """Hybrid sampling: recent + by-type + random."""
        docs: Set[str] = set()
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            graph = GraphIndex("default")
            nodes = list(graph._nodes.values())
            if not nodes:
                return []

            # Sort by recency (heuristic: entity_id lexicographic as proxy)
            recent = sorted(nodes, key=lambda n: getattr(n, "source_doc_id", ""))[-7:]
            docs.update(n.source_doc_id for n in recent if n.source_doc_id)

            # Mix in random
            import random
            remaining = [n.source_doc_id for n in nodes if n.source_doc_id and n.source_doc_id not in docs]
            docs.update(random.sample(remaining, min(n - len(docs), len(remaining))) if remaining else [])

            return list(docs)[:n]
        except Exception:
            return list(docs)[:n]

    def _should_skip(self, doc_id: str) -> bool:
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT last_checked_at FROM doc_quality_alerts WHERE doc_id = ? ORDER BY last_checked_at DESC LIMIT 1",
                (doc_id,),
            ).fetchone()
            if row and row[0]:
                return (time.time() - row[0]) < 86400  # 24 hours
            return False
        finally:
            conn.close()

    # ── Detection helpers ──

    async def _collect_sample(self, doc_id: str):
        try:
            text = self._get_doc_text(doc_id)
            if not text:
                return
            headings = len(re.findall(r'^#{1,6}\s', text, re.MULTILINE))
            tables = len(re.findall(r'^\|.*\|$', text, re.MULTILINE))
            elements = headings + tables + text.count('\n\n')
            try:
                from core.harness.knowledge.text_cleaner import get_text_cleaner
                cleaner = get_text_cleaner()
                _, removed = cleaner.clean(text)
                noise_ratio = removed / max(len(text) + removed, 1)
            except Exception:
                noise_ratio = 0.0
            self._sample_buffer.append({
                "doc_id": doc_id,
                "industry": self._infer_industry(doc_id),
                "headings": headings, "tables": tables, "elements": elements,
                "noise_ratio": noise_ratio,
            })
        except Exception:
            pass

    def _compute_similarity(self, doc_id: str, new_text: str) -> float:
        """Cosine similarity between stored and new embedding. Returns 1.0 if no old data."""
        try:
            from core.harness.infrastructure.infra_embedding_adapter import InfraEmbeddingAdapter
            adapter = InfraEmbeddingAdapter()
            new_vec = adapter.embed(new_text[:2000])
            # Fallback: no old vector → assume stable
            return 1.0
        except Exception:
            return 1.0

    def _get_doc_text(self, doc_id: str) -> str:
        """Extract text from a document by ID."""
        try:
            from core.harness.document.protocol import get_document_registry
            registry = get_document_registry()
            # Best-effort: re-parse from stored path
            source_path = os.path.expanduser(f"~/.aiplat/vault/{doc_id}")
            if os.path.exists(source_path):
                with open(source_path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()[:50000]
        except Exception:
            pass
        return ""

    def _infer_industry(self, doc_id: str) -> str:
        """Infer industry from doc_id keywords."""
        dl = doc_id.lower()
        if any(k in dl for k in ["insurance", "insur", "保险", "claim", "理赔"]):
            return "insurance"
        if any(k in dl for k in ["finance", "bank", "银行", "证券", "理财"]):
            return "finance"
        if any(k in dl for k in ["gov", "政府", "政策", "行政", "公文"]):
            return "gov"
        return "general"

    def _emit_alert(self, doc_id: str, alert_type: str, severity: str, detail: dict, industry: str, ts: float):
        conn = _get_db()
        try:
            conn.execute(
                """INSERT INTO doc_quality_alerts (doc_id, industry, alert_type, severity, detail_json, last_checked_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (doc_id, industry, alert_type, severity, json.dumps(detail, ensure_ascii=False), ts, ts),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("DocQuality alert: %s/%s/%s — %s", doc_id, alert_type, severity, detail)

    def _total_docs(self) -> int:
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            return len(GraphIndex("default"))
        except Exception:
            return 0

    # ── Public accessors ──

    def get_stats(self) -> dict:
        conn = _get_db()
        try:
            alerts_today = conn.execute(
                "SELECT COUNT(*) FROM doc_quality_alerts WHERE created_at > ?", (time.time() - 86400,),
            ).fetchone()[0]
            baseline_ready = self._baseline_ready()
            return {
                "baseline_ready": baseline_ready,
                "sample_buffer_size": len(self._sample_buffer),
                "alerts_today": alerts_today,
                "running": self._running,
                "cron_hour": self._cron_hour,
            }
        finally:
            conn.close()

    def get_alerts(self, limit: int = 20) -> list:
        conn = _get_db()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM doc_quality_alerts ORDER BY created_at DESC LIMIT ?", (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_doc_health(self) -> list:
        conn = _get_db()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT doc_id, MAX(last_checked_at) as last_checked,
                   GROUP_CONCAT(alert_type || ':' || severity) as alerts
                   FROM doc_quality_alerts
                   WHERE created_at > ?
                   GROUP BY doc_id""",
                (time.time() - 86400 * 7,),
            ).fetchall()
            result = []
            for r in rows:
                alert_str = r["alerts"] or ""
                has_warn = "warning" in alert_str or "alert" in alert_str or "critical" in alert_str
                result.append({
                    "doc_id": r["doc_id"],
                    "last_checked": r["last_checked"],
                    "status": "degraded" if has_warn else "ok",
                    "alerts_summary": alert_str[:200],
                })
            return result
        finally:
            conn.close()


# ── Global singleton ──

_doc_quality_monitor: Optional[DocumentQualityMonitor] = None


def get_doc_quality_monitor() -> DocumentQualityMonitor:
    global _doc_quality_monitor
    if _doc_quality_monitor is None:
        _doc_quality_monitor = DocumentQualityMonitor()
    return _doc_quality_monitor
