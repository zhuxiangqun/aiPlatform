"""Hermeticity: ExecutionStore defaults must not escape to ~/.aiplat under AIPLAT_HOME."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_pytest_configure_pins_execution_and_platform_db_under_tmp():
    home = Path(os.environ["AIPLAT_HOME"])
    assert "aiplat-pytest" in str(home)
    exec_path = Path(os.environ["AIPLAT_EXECUTION_DB_PATH"])
    plat_path = Path(os.environ["AIPLAT_PLATFORM_DB_PATH"])
    action_path = Path(os.environ["AIPLAT_ACTION_DB_PATH"])
    profile_dir = Path(os.environ["AIPLAT_PROFILE_DIR"])
    for p in (exec_path, plat_path, action_path, profile_dir):
        assert str(p).startswith(str(home))
    # Must not be the developer symlink target under the repo.
    assert "core/data/aiplat_executions.sqlite3" not in str(exec_path)
    assert str(action_path) != "data/execution_store.db"
    assert "./data/execution_store.db" not in str(action_path)


def test_default_execution_db_path_respects_aiplat_home(monkeypatch, tmp_path):
    from core.services.execution_store import default_execution_db_path, reset_execution_store

    reset_execution_store()
    monkeypatch.delenv("AIPLAT_EXECUTION_DB_PATH", raising=False)
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    assert default_execution_db_path() == str(tmp_path / "aiplat_executions.sqlite3")


def test_default_execution_db_path_env_wins(monkeypatch, tmp_path):
    from core.services.execution_store import default_execution_db_path

    explicit = str(tmp_path / "custom.sqlite3")
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", explicit)
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "ignored"))
    assert default_execution_db_path() == explicit


def test_get_execution_store_uses_pinned_path():
    from core.services.execution_store import get_execution_store, reset_execution_store

    reset_execution_store()
    store = get_execution_store()
    pinned = os.environ["AIPLAT_EXECUTION_DB_PATH"]
    cfg_path = str(getattr(getattr(store, "_config", None), "db_path", ""))
    assert cfg_path == pinned
    assert "aiplat-pytest" in cfg_path
    reset_execution_store()


@pytest.mark.skipif(
    not Path(__file__).resolve().parents[5].joinpath("aiPlat-platform").is_dir(),
    reason="platform checkout missing",
)
def test_tenant_store_default_respects_aiplat_home(monkeypatch, tmp_path):
    import sys

    plat = str(Path(__file__).resolve().parents[5] / "aiPlat-platform")
    if plat not in sys.path:
        sys.path.insert(0, plat)
    from tenants.tenant_store import TenantStore  # type: ignore

    monkeypatch.delenv("AIPLAT_EXECUTION_DB_PATH", raising=False)
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    ts = TenantStore()
    assert ts._db_path == str(tmp_path / "aiplat_executions.sqlite3")
