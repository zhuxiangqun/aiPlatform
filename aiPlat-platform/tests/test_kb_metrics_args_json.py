"""KB metrics must read syscall_events.args_json / result_json (not payload)."""
from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

from kb.metrics import KBMetrics, _query_syscall_metrics


def _make_db(rows: list) -> str:
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    Path(path).unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE syscall_events (
            id INTEGER PRIMARY KEY,
            kind TEXT,
            name TEXT,
            args_json TEXT,
            result_json TEXT,
            created_at REAL,
            tenant_id TEXT
        )
        """
    )
    now = time.time()
    for kind, name, args_json, result_json, age_h in rows:
        conn.execute(
            "INSERT INTO syscall_events(kind,name,args_json,result_json,created_at,tenant_id) "
            "VALUES (?,?,?,?,?,?)",
            (kind, name, args_json, result_json, now - age_h * 3600, "t1"),
        )
    conn.commit()
    conn.close()
    return path


def test_query_syscall_metrics_uses_result_json_not_payload():
    path = _make_db(
        [
            (
                "knowledge_retrieve",
                "sys_knowledge_retrieve",
                '{"question":"差旅报销标准"}',
                '{"count":0,"items":[]}',
                1,
            ),
            (
                "kb",
                "sys_kb_retrieve",
                '{"question":"年假"}',
                '{"count":2,"items":[{"source":"手册.pdf","score":0.9}],"citations":[{"doc":"手册.pdf"}]}',
                2,
            ),
            (
                "feedback",
                "user_feedback",
                '{"type":"error","question":"坏答案"}',
                "{}",
                1,
            ),
        ]
    )
    try:
        m = KBMetrics(window_hours=24)
        conn = sqlite3.connect(path)
        try:
            _query_syscall_metrics(m, conn, window_hours=24, tenant_id="")
        finally:
            conn.close()
        assert m.total_queries == 2
        assert m.no_answer_rate == 0.5
        assert m.citation_coverage == 0.5
        assert m.error_correction_rate == 0.5  # 1 feedback error / 2 retrieve
    finally:
        Path(path).unlink(missing_ok=True)


def test_query_matches_name_like_without_kind():
    path = _make_db(
        [
            (
                "syscall",
                "sys_knowledge_retrieve",
                '{"q":"x"}',
                '{"items":[]}',
                0.5,
            ),
        ]
    )
    try:
        m = KBMetrics(window_hours=24)
        conn = sqlite3.connect(path)
        try:
            _query_syscall_metrics(m, conn, window_hours=24, tenant_id="")
        finally:
            conn.close()
        assert m.total_queries == 1
        assert m.no_answer_rate == 1.0
    finally:
        Path(path).unlink(missing_ok=True)
