u"""
Usage Tracker — Agent/domain 级计量引擎 (v2.6).

Tracks: sys_llm_generate, sys_tool_call, sys_skill_call, sys_knowledge_retrieve
Storage: ~/.aiplat/usage_metrics.db (SQLite with daily aggregation)
"""
from __future__ import annotations

import json as _json
import logging
import os as _os
import sqlite3 as _sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usage_tracker")

_DB_PATH = _os.path.expanduser("~/.aiplat/usage_metrics.db")
_FLUSH_INTERVAL = 5.0  # seconds between batch flushes
_BATCH_SIZE = 100      # max events before forced flush

_event_queue: List[Dict[str, Any]] = []
_last_flush = 0.0


def _get_conn() -> _sqlite3.Connection:
    conn = _sqlite3.connect(_DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _init_db() -> None:
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            domain_id TEXT DEFAULT '',
            agent_id TEXT DEFAULT '',
            tenant_id TEXT DEFAULT '',
            session_id TEXT DEFAULT '',
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            latency_ms REAL DEFAULT 0,
            status TEXT DEFAULT 'success'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_daily_agg (
            date TEXT NOT NULL,
            domain_id TEXT DEFAULT '',
            agent_id TEXT DEFAULT '',
            tenant_id TEXT DEFAULT '',
            total_calls INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            avg_latency_ms REAL DEFAULT 0,
            unique_sessions INTEGER DEFAULT 0,
            PRIMARY KEY (date, domain_id, agent_id, tenant_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domain_assets (
            domain_id TEXT PRIMARY KEY,
            entity_count INTEGER DEFAULT 0,
            edge_count INTEGER DEFAULT 0,
            wiki_page_count INTEGER DEFAULT 0,
            last_updated TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def record(event_type: str, *,
           domain_id: str = "",
           agent_id: str = "",
           tenant_id: str = "",
           session_id: str = "",
           tokens_in: int = 0,
           tokens_out: int = 0,
           latency_ms: float = 0,
           status: str = "success") -> None:
    u"""Record a usage event. Batched writes for performance."""
    global _event_queue, _last_flush
    _event_queue.append({
        "timestamp": time.time(),
        "event_type": event_type,
        "domain_id": domain_id,
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "status": status,
    })
    now = time.time()
    if len(_event_queue) >= _BATCH_SIZE or (now - _last_flush) > _FLUSH_INTERVAL:
        _flush()
        _last_flush = now


def _flush() -> None:
    global _event_queue
    if not _event_queue:
        return
    try:
        conn = _get_conn()
        batch = _event_queue[:]
        _event_queue = []
        conn.executemany(
            "INSERT INTO usage_events (timestamp, event_type, domain_id, agent_id, tenant_id, session_id, tokens_in, tokens_out, latency_ms, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(e["timestamp"], e["event_type"], e["domain_id"], e["agent_id"], e["tenant_id"],
              e["session_id"], e["tokens_in"], e["tokens_out"], e["latency_ms"], e["status"])
             for e in batch],
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.debug("Usage flush failed (non-critical): %s", exc)
        _event_queue = batch + _event_queue


def aggregate_daily() -> None:
    u"""Run daily aggregation from raw events to usage_daily_agg."""
    try:
        conn = _get_conn()
        today = time.strftime("%Y-%m-%d", time.gmtime())
        conn.execute("""
            INSERT OR REPLACE INTO usage_daily_agg (date, domain_id, agent_id, tenant_id, total_calls, total_tokens, avg_latency_ms, unique_sessions)
            SELECT
                date(?, 'unixepoch') as date,
                domain_id, agent_id, tenant_id,
                COUNT(*) as total_calls,
                SUM(tokens_in + tokens_out) as total_tokens,
                AVG(latency_ms) as avg_latency_ms,
                COUNT(DISTINCT session_id) as unique_sessions
            FROM usage_events
            WHERE date(timestamp, 'unixepoch') = date(?, 'unixepoch')
            GROUP BY date(?, 'unixepoch'), domain_id, agent_id, tenant_id
        """, (time.time(), time.time(), time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Daily aggregation failed: %s", e)


def update_domain_assets(domain_id: str, entity_count: int = 0, edge_count: int = 0,
                          wiki_page_count: int = 0) -> None:
    u"""Update domain asset counts (entities, edges, wiki pages)."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO domain_assets (domain_id, entity_count, edge_count, wiki_page_count, last_updated) VALUES (?, ?, ?, ?, ?)",
            (domain_id, entity_count, edge_count, wiki_page_count, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Domain asset update failed: %s", e)


def get_domain_stats(domain_id: str = "", days: int = 7) -> List[Dict[str, Any]]:
    u"""Get usage stats per domain for the last N days."""
    try:
        conn = _get_conn()
        _init_db()
        if domain_id:
            rows = conn.execute(
                "SELECT date, domain_id, SUM(total_calls), SUM(total_tokens), AVG(avg_latency_ms) FROM usage_daily_agg WHERE domain_id=? AND date >= date('now', ? || ' days') GROUP BY date, domain_id ORDER BY date",
                (domain_id, f"-{days}"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT date, domain_id, SUM(total_calls), SUM(total_tokens), AVG(avg_latency_ms) FROM usage_daily_agg WHERE date >= date('now', ? || ' days') GROUP BY date, domain_id ORDER BY date",
                (f"-{days}",),
            ).fetchall()
        conn.close()
        return [
            {"date": r[0], "domain_id": r[1], "total_calls": r[2], "total_tokens": r[3], "avg_latency_ms": round(r[4] or 0, 2)}
            for r in rows
        ]
    except Exception as e:
        logger.warning("get_domain_stats failed: %s", e)
        return []


def get_agent_stats(agent_id: str = "", days: int = 7) -> List[Dict[str, Any]]:
    u"""Get usage stats per agent for the last N days."""
    try:
        conn = _get_conn()
        _init_db()
        if agent_id:
            rows = conn.execute(
                "SELECT date, agent_id, SUM(total_calls), SUM(total_tokens) FROM usage_daily_agg WHERE agent_id=? AND date >= date('now', ? || ' days') GROUP BY date, agent_id ORDER BY date",
                (agent_id, f"-{days}"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT date, agent_id, SUM(total_calls), SUM(total_tokens) FROM usage_daily_agg WHERE date >= date('now', ? || ' days') GROUP BY date, agent_id ORDER BY date",
                (f"-{days}",),
            ).fetchall()
        conn.close()
        return [
            {"date": r[0], "agent_id": r[1], "total_calls": r[2], "total_tokens": r[3]}
            for r in rows
        ]
    except Exception as e:
        logger.warning("get_agent_stats failed: %s", e)
        return []


_get_conn()  # auto-init on import
