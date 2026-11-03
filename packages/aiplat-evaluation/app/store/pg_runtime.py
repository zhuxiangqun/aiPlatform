"""Sync bridge over asyncpg for B1-L Postgres EvalStore.

Honesty: local engineering only; process_split_authorized stays false.
Driver: asyncpg (monorepo-available); optional until postgres URL is used.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Awaitable, Callable, Sequence, TypeVar

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run an awaitable from sync code (FastAPI sync routes / scripts)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def qmark_to_dollar(sql: str) -> str:
    """Rewrite sqlite-style ? placeholders to asyncpg $1..$n."""
    out: list[str] = []
    n = 0
    for ch in sql:
        if ch == "?":
            n += 1
            out.append(f"${n}")
        else:
            out.append(ch)
    return "".join(out)


def require_asyncpg():
    try:
        import asyncpg  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Postgres AIPLAT_EVAL_DB_URL requires asyncpg "
            "(pip install asyncpg). SQLite remains the default backend."
        ) from exc
    return __import__("asyncpg")


async def _with_connection(dsn: str, fn: Callable[[Any], Awaitable[T]]) -> T:
    asyncpg = require_asyncpg()
    conn = await asyncpg.connect(dsn)
    try:
        return await fn(conn)
    finally:
        await conn.close()


def pg_fetch(dsn: str, sql: str, args: Sequence[Any] = ()) -> list[Any]:
    pg_sql = qmark_to_dollar(sql)

    async def _run(conn):
        return await conn.fetch(pg_sql, *args)

    return list(run_async(_with_connection(dsn, _run)))


def pg_fetchrow(dsn: str, sql: str, args: Sequence[Any] = ()) -> Any | None:
    pg_sql = qmark_to_dollar(sql)

    async def _run(conn):
        return await conn.fetchrow(pg_sql, *args)

    return run_async(_with_connection(dsn, _run))


def pg_fetchval(dsn: str, sql: str, args: Sequence[Any] = ()) -> Any:
    pg_sql = qmark_to_dollar(sql)

    async def _run(conn):
        return await conn.fetchval(pg_sql, *args)

    return run_async(_with_connection(dsn, _run))


def pg_execute(dsn: str, sql: str, args: Sequence[Any] = ()) -> str:
    pg_sql = qmark_to_dollar(sql)

    async def _run(conn):
        return await conn.execute(pg_sql, *args)

    return run_async(_with_connection(dsn, _run))


def pg_execute_script(dsn: str, statements: Sequence[str]) -> None:
    async def _run(conn):
        async with conn.transaction():
            for stmt in statements:
                await conn.execute(stmt)

    run_async(_with_connection(dsn, _run))


def _probe_qmark() -> str:
    """Same-file warm call for method_verify."""
    return qmark_to_dollar("SELECT ? WHERE x=?")
