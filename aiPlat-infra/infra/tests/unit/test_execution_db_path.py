"""execution_db_path default must match CredentialPool so API adapters are discoverable."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def test_execution_db_path_defaults_to_home(monkeypatch):
    from infra.management.model.paths import execution_db_path

    monkeypatch.delenv("AIPLAT_EXECUTION_DB_PATH", raising=False)
    assert execution_db_path().endswith(".aiplat/aiplat_executions.sqlite3")


def test_execution_db_path_env_override(monkeypatch, tmp_path):
    from infra.management.model.paths import execution_db_path

    p = tmp_path / "custom.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(p))
    assert execution_db_path() == str(p)


def test_load_adapter_models_uses_home_default(monkeypatch, tmp_path):
    """Without AIPLAT_EXECUTION_DB_PATH, adapters under ~/.aiplat default must still load.

    Regression: empty-string default skipped DeepSeek/API models from ModelManager.
    """
    from infra.management.model import config_loader as cl

    db = tmp_path / "aiplat_executions.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE adapters (
            adapter_id TEXT PRIMARY KEY,
            name TEXT,
            provider TEXT,
            api_base_url TEXT,
            models_json TEXT,
            capabilities_json TEXT,
            model_type TEXT,
            api_key TEXT,
            api_key_enc TEXT,
            status TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO adapters (
            adapter_id, name, provider, api_base_url, models_json,
            capabilities_json, model_type, api_key, api_key_enc, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "adapter-deepseek-test",
            "DeepSeek",
            "deepseek",
            "https://api.deepseek.com",
            json.dumps([{"name": "deepseek-chat"}]),
            "[]",
            "chat",
            "sk-live-placeholder-key-xyz",
            None,
            "active",
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.delenv("AIPLAT_EXECUTION_DB_PATH", raising=False)
    monkeypatch.setattr(
        "infra.management.model.paths.execution_db_path",
        lambda: str(db),
    )

    models = cl._load_adapter_models()
    names = {m.name for m in models}
    assert "deepseek-chat" in names, names
    ds = next(m for m in models if m.name == "deepseek-chat")
    assert ds.provider == "deepseek"
