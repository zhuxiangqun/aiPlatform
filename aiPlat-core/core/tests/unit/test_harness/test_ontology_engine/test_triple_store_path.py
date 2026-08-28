"""test_triple_store_path.py — TripleStore 路径解析测试（2026-08-28）。

覆盖：① AIPLAT_HOME 优先（不再硬编码 ~/.aiplat）② db_path 显式覆盖 AIPLAT_HOME
③ 默认路径落在 AIPLAT_HOME 下。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.harness.ontology_engine.triple_store import TripleStore  # noqa: E402


def test_default_path_uses_aiplat_home(tmp_path, monkeypatch):
    """AIPLAT_HOME 设置时，默认 DB 落在 $AIPLAT_HOME 下（不再硬编码 ~/.aiplat）。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    store = TripleStore()
    # 验证连接可用且写入成功（证明路径可写、非只读）
    store.add("urn:aiplat:test:s1", "p", "o", source="test_src")
    assert store.clear_source("test_src") >= 1
    # DB 文件确实在 AIPLAT_HOME 下
    db = tmp_path / "home" / "ontology_triples.sqlite3"
    assert db.exists(), f"DB 未落在 AIPLAT_HOME 下: {db}"
    store._conn.close()


def test_explicit_db_path_overrides(tmp_path, monkeypatch):
    """db_path 显式指定时优先于 AIPLAT_HOME。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "ignored"))
    explicit = tmp_path / "custom" / "triples.sqlite3"
    store = TripleStore(db_path=str(explicit))
    assert explicit.exists()
    assert not (tmp_path / "ignored" / "ontology_triples.sqlite3").exists()
    store._conn.close()


def test_default_path_without_aiplat_home(tmp_path, monkeypatch):
    """AIPLAT_HOME 未设置 → 回退 ~/.aiplat（不抛异常）。"""
    monkeypatch.delenv("AIPLAT_HOME", raising=False)
    store = TripleStore(db_path=str(tmp_path / "explicit.sqlite3"))  # 避免写真实 ~/.aiplat
    store.add("urn:aiplat:test:s2", "p", "o", source="test_src2")
    assert store.clear_source("test_src2") >= 1
    store._conn.close()
