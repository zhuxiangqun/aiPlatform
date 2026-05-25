"""Reusable aiohttp ClientSession singleton.

NOTE: This module is implemented but awaiting wiring. Embedding, MCP admin,
health checker, and other call sites currently create their own inline sessions.
Wire by replacing `aiohttp.ClientSession()` calls with `await get_session()`.

Usage:
    from core.utils.aiohttp_session import get_session
    async with await get_session() as session:
        async with session.get(url) as resp: ...
"""
import asyncio
from typing import Optional
import aiohttp


_session: Optional[aiohttp.ClientSession] = None
_lock = asyncio.Lock()


async def get_session() -> aiohttp.ClientSession:
    """Get or create the persistent aiohttp session singleton."""
    global _session
    if _session is not None and not _session.closed:
        return _session
    async with _lock:
        if _session is not None and not _session.closed:
            return _session
        _session = aiohttp.ClientSession()
        return _session


async def close_session():
    """Close the persistent session (called during shutdown)."""
    global _session
    if _session is not None:
        await _session.close()
        _session = None
