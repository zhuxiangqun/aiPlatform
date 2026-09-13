"""Shared paths for model management (adapters / credentials / health)."""

from __future__ import annotations

import os


def execution_db_path() -> str:
    """SQLite path for adapters + credentials (single source of truth).

    Must stay aligned across ConfigLoader, CredentialPool, and health checks.
    Env ``AIPLAT_EXECUTION_DB_PATH`` overrides; otherwise ``~/.aiplat/aiplat_executions.sqlite3``.
    """
    return os.getenv(
        "AIPLAT_EXECUTION_DB_PATH",
        os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3"),
    )
