"""test_model_health.py — Model 健康诊断时效窗口测试（2026-08-28）。

覆盖：① 历史失败（>stale_days）不计入 → pass ② 近期失败 → fail ③ 无时间戳失败 → 保守 fail
④ DB 路径 AIPLAT_HOME 优先 ⑤ 表缺失降级 warn。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.diagnostics.checks.model_health import (  # noqa: E402
    check_model_health, _parse_ts,
)


def _make_db(tmp_path, rows):
    """构造 model_health 测试库。rows: [(name, success, fail, last_failure_at)]"""
    db = tmp_path / "exec.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE model_health (
        model_name TEXT, success_count INT, failure_count INT, call_count INT,
        business_score REAL, last_failure_at TEXT)""")
    for name, ok, fail, last in rows:
        conn.execute(
            "INSERT INTO model_health VALUES (?,?,?,?,?,?)",
            (name, ok, fail, ok + fail, 0.5, last))
    conn.commit()
    conn.close()
    return str(db)


def _iso(days_ago: int) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def test_stale_failures_ignored(tmp_path, monkeypatch):
    """历史失败（12 天前）→ 不计入，诊断 pass。"""
    db = _make_db(tmp_path, [
        ("qwen2.5-coder:7b", 8, 99, _iso(12)),  # 历史集中失败
        ("deepseek-chat", 1000, 10, _iso(3)),    # 近期少量失败（率 99% > 80% → 不计 warn）
    ])
    monkeypatch.setenv("AIPLAT_MODEL_HEALTH_DB", db)
    r = pytest.importorskip("asyncio").run(check_model_health(stale_days=7))
    assert r["status"] == "pass", f"历史失败应忽略: {r}"


def test_recent_failures_flag_fail(tmp_path, monkeypatch):
    """近期集中失败（1 天前）→ fail。"""
    db = _make_db(tmp_path, [
        ("ollama-local", 0, 50, _iso(1)),
    ])
    monkeypatch.setenv("AIPLAT_MODEL_HEALTH_DB", db)
    r = pytest.importorskip("asyncio").run(check_model_health(stale_days=7))
    assert r["status"] == "fail"
    assert r["models"][0]["model"] == "ollama-local"


def test_recent_low_rate_warns(tmp_path, monkeypatch):
    """近期成功率 <80% → warn（非 fail）。"""
    db = _make_db(tmp_path, [
        ("mixed", 7, 3, _iso(1)),  # 成功率 70% < 80%
    ])
    monkeypatch.setenv("AIPLAT_MODEL_HEALTH_DB", db)
    r = pytest.importorskip("asyncio").run(check_model_health(stale_days=7))
    assert r["status"] == "warn"


def test_no_timestamp_conservative_fail(tmp_path, monkeypatch):
    """有失败但无时间戳 → 保守计入 fail（无法确认时效）。"""
    db = _make_db(tmp_path, [
        ("unknown-age", 0, 20, None),
    ])
    monkeypatch.setenv("AIPLAT_MODEL_HEALTH_DB", db)
    r = pytest.importorskip("asyncio").run(check_model_health(stale_days=7))
    assert r["status"] == "fail"


def test_missing_table_warns(tmp_path, monkeypatch):
    """表缺失 → 降级 warn（不崩溃）。"""
    db = tmp_path / "empty.sqlite3"
    sqlite3.connect(str(db)).close()
    monkeypatch.setenv("AIPLAT_MODEL_HEALTH_DB", str(db))
    r = pytest.importorskip("asyncio").run(check_model_health())
    assert r["status"] == "warn"


def test_parse_ts_formats():
    assert _parse_ts("2026-08-16T12:51:34") is not None
    assert _parse_ts("2026-08-16") is not None
    assert _parse_ts(None) is None
    assert _parse_ts("garbage") is None
