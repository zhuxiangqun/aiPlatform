"""
Unified SQLite connection layer for aiPlat-core.

All modules must use get_db_connection() or create_persistent_conn()
instead of raw sqlite3.connect() to ensure:

  1. WAL journal mode (enables concurrent reads during writes)
  2. busy_timeout=3000 (waits 3s on lock contention instead of SQLITE_BUSY)
  3. Consistent row_factory = sqlite3.Row
  4. Auto commit/rollback/close via context manager (cold paths)
  5. Persistent connections with asyncio.Lock (hot paths like state_history)

Global WAL enablement is done once at startup via ensure_wal_enabled().
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger("aiplat.db_utils")

_DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3",
)


def _pragma_wal(conn: sqlite3.Connection, *, attempts: int = 8) -> None:
    """Set WAL with retry — gunicorn multi-worker boot races on first open."""
    last: Optional[BaseException] = None
    for i in range(max(1, attempts)):
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as e:
            last = e
            if "locked" not in str(e).lower():
                raise
            time.sleep(0.05 * (i + 1))
    if last is not None:
        raise last


def ensure_wal_enabled(db_path: Optional[str] = None) -> None:
    """Ensure WAL mode for a SQLite file. Called once at startup.

    Args:
        db_path: db_path 参数。
    """
    path = db_path or _DEFAULT_DB_PATH
    if not os.path.exists(path):
        return
    try:
        conn = sqlite3.connect(path, timeout=3.0)
        _pragma_wal(conn)
        conn.close()
        logger.debug("WAL enabled for %s", path)
    except Exception:
        logger.debug("ensure_wal_enabled skipped for %s", path, exc_info=True)


@contextmanager
def get_db_connection(
    db_path: Optional[str] = None,
    *,
    wal: bool = True,
    busy_timeout: int = 3000,
) -> Generator[sqlite3.Connection, None, None]:
    """Unified SQLite connection context manager.

    Args:
        db_path: db_path 参数。
        wal: wal 参数。
        busy_timeout: busy_timeout 参数。
    """
    path = db_path or _DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)

    conn = sqlite3.connect(path, timeout=busy_timeout / 1000.0)
    conn.row_factory = sqlite3.Row

    if wal:
        _pragma_wal(conn)
    conn.execute(f"PRAGMA busy_timeout={busy_timeout}")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_persistent_conn(
    db_path: Optional[str] = None,
    *,
    wal: bool = True,
    busy_timeout: int = 3000,
) -> sqlite3.Connection:
    """Create a persistent connection for hot-path modules.

    Args:
        db_path: db_path 参数。
        wal: wal 参数。
        busy_timeout: busy_timeout 参数。
    """
    path = db_path or _DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)

    conn = sqlite3.connect(path, timeout=busy_timeout / 1000.0)
    conn.row_factory = sqlite3.Row

    if wal:
        _pragma_wal(conn)
    conn.execute(f"PRAGMA busy_timeout={busy_timeout}")

    return conn
