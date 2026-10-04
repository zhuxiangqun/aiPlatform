"""Adapter → ModelManager injection must not crash and must register all models."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def test_do_inject_adapter_models_registers_all_deepseek_models(tmp_path, monkeypatch):
    from core.harness.utils import model_injection as mi
    from infra.management.schemas import ModelInfo, ModelType, ModelSource, ModelStatus

    db = tmp_path / "exec.sqlite3"
    con = sqlite3.connect(str(db))
    con.execute(
        """
        CREATE TABLE adapters (
          adapter_id TEXT, name TEXT, provider TEXT, status TEXT,
          api_base_url TEXT, models_json TEXT, api_key TEXT, api_key_enc TEXT,
          updated_at REAL
        )
        """
    )
    con.execute(
        """
        INSERT INTO adapters VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            "adapter-ds",
            "DeepSeek",
            "deepseek",
            "active",
            "https://api.deepseek.com/v1",
            json.dumps(
                [{"name": "deepseek-chat"}, {"name": "deepseek-v4-pro"}]
            ),
            "sk-live-realkey-abcdef0123456789",
            None,
            1.0,
        ),
    )
    con.commit()
    con.close()

    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db))

    class _Mgr:
        def __init__(self):
            self._models = {}

    mgr = _Mgr()
    # Avoid pulling kernel runtime; env path is enough.
    n = mi._do_inject_adapter_models(mgr)
    assert n == 2
    assert "deepseek-chat" in mgr._models
    assert "deepseek-v4-pro" in mgr._models
    assert mgr._models["deepseek-chat"].provider == "deepseek"
    assert mgr._models["deepseek-chat"].source == ModelSource.EXTERNAL


def test_do_inject_skips_invalid_api_key(tmp_path, monkeypatch):
    from core.harness.utils import model_injection as mi

    db = tmp_path / "exec.sqlite3"
    con = sqlite3.connect(str(db))
    con.execute(
        """
        CREATE TABLE adapters (
          adapter_id TEXT, name TEXT, provider TEXT, status TEXT,
          api_base_url TEXT, models_json TEXT, api_key TEXT, api_key_enc TEXT,
          updated_at REAL
        )
        """
    )
    con.execute(
        "INSERT INTO adapters VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "adapter-bad",
            "Bad",
            "deepseek",
            "active",
            "https://api.deepseek.com/v1",
            json.dumps([{"name": "deepseek-chat"}]),
            "not-a-real-key",
            None,
            1.0,
        ),
    )
    con.commit()
    con.close()
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db))

    class _Mgr:
        def __init__(self):
            self._models = {}

    assert mi._do_inject_adapter_models(_Mgr()) == 0
