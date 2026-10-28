"""Shared pytest fixtures for core tests.

Hermeticity (pytest_configure): pin AIPLAT_HOME + execution/platform DB paths to a
session tempdir *before* collection/import so stores cannot escape to ~/.aiplat
or the repo-linked production sqlite (see expand-green review Oct 2026).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_HERMETIC_HOME: Path | None = None
_SAVED_ENV: dict[str, str | None] = {}


def _pin_env(key: str, value: str) -> None:
    if key not in _SAVED_ENV:
        _SAVED_ENV[key] = os.environ.get(key)
    os.environ[key] = value


def pytest_configure(config: pytest.Config) -> None:
    """Force all store defaults under a disposable home before imports run."""
    global _HERMETIC_HOME
    home = Path(tempfile.mkdtemp(prefix="aiplat-pytest-"))
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "profiles").mkdir(parents=True, exist_ok=True)
    _HERMETIC_HOME = home

    _pin_env("AIPLAT_HOME", str(home))
    _pin_env("AIPLAT_EXECUTION_DB_PATH", str(home / "aiplat_executions.sqlite3"))
    _pin_env("AIPLAT_PLATFORM_DB_PATH", str(home / "data" / "aiplat_platform.sqlite3"))
    _pin_env("AIPLAT_ACTION_DB_PATH", str(home / "data" / "action_store.sqlite3"))
    _pin_env("AIPLAT_PROFILE_DIR", str(home / "profiles"))

    # Seed minimal llm_profile so model injection works without real ~/.aiplat.
    profile = home / "profiles" / "llm_profile.yaml"
    if not profile.exists():
        profile.write_text(
            "version: 1\npurposes: {}\naliases: {}\nlocal_only: false\n",
            encoding="utf-8",
        )


def pytest_unconfigure(config: pytest.Config) -> None:
    """Drop store singletons and restore env; remove hermetic home."""
    try:
        from core.services.execution_store import reset_execution_store

        reset_execution_store()
    except Exception:
        pass

    for key, old in list(_SAVED_ENV.items()):
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
    _SAVED_ENV.clear()

    global _HERMETIC_HOME
    if _HERMETIC_HOME is not None:
        try:
            shutil.rmtree(_HERMETIC_HOME, ignore_errors=True)
        except Exception:
            pass
        _HERMETIC_HOME = None


@pytest.fixture(scope="session", autouse=True)
def _session_hermetic_home():
    """Keep AIPLAT_HOME pointing at the pytest_configure temp for the session.

    Also reset ExecutionStore at session end (in addition to pytest_unconfigure)
    so late fixtures cannot leave a live handle on the temp DB.
    """
    home = Path(os.environ.get("AIPLAT_HOME") or (_HERMETIC_HOME or ""))
    if not home or not str(home):
        home = Path(tempfile.mkdtemp(prefix="aiplat-pytest-fallback-"))
        os.environ["AIPLAT_HOME"] = str(home)
        os.environ.setdefault(
            "AIPLAT_EXECUTION_DB_PATH", str(home / "aiplat_executions.sqlite3")
        )
        os.environ.setdefault(
            "AIPLAT_PLATFORM_DB_PATH", str(home / "data" / "aiplat_platform.sqlite3")
        )
        (home / "data").mkdir(parents=True, exist_ok=True)
        (home / "profiles").mkdir(parents=True, exist_ok=True)

    profile = home / "profiles" / "llm_profile.yaml"
    if not profile.exists():
        profile.write_text(
            "version: 1\npurposes: {}\naliases: {}\nlocal_only: false\n",
            encoding="utf-8",
        )
    yield
    try:
        from core.services.execution_store import reset_execution_store

        reset_execution_store()
    except Exception:
        pass
    try:
        from core.harness.ontology_engine import state_history as sh

        sh.close_connection()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _isolate_shared_state():
    """Clean up global singletons between tests to prevent cross-test contamination."""
    # Drop process-global git env left by inline-autoreview helpers so later
    # ``git init`` in tmp_path is not pointed at a deleted worktree.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"):
        os.environ.pop(key, None)
    yield
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"):
        os.environ.pop(key, None)
    try:
        import core.harness.memory.shared_pool as sp

        if sp._pool is not None and hasattr(sp._pool, "_db_conn") and sp._pool._db_conn:
            try:
                sp._pool._db_conn.close()
            except Exception:
                pass
        sp._pool = None
    except Exception:
        pass
    try:
        import core.harness.optimization.strategy_tracker as st

        st._tracker = None
    except Exception:
        pass
    try:
        import core.harness.optimization.search_engine as se

        se._engine = None
    except Exception:
        pass
