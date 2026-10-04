"""ExecutionStore.init must not deadlock when prune re-enters init."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.services.execution_store._base import ExecutionStoreConfig
from core.services.execution_store import ExecutionStore


@pytest.mark.asyncio
async def test_init_with_prune_does_not_deadlock(tmp_path: Path):
    """prune_on_start used to call prune() while holding _init_once_lock → forever hang."""
    db = tmp_path / "exec.sqlite3"
    store = ExecutionStore(
        ExecutionStoreConfig(
            db_path=str(db),
            prune_on_start=True,
            retention_days=7,
            max_rows_per_entity=1000,
        )
    )
    await asyncio.wait_for(store.init(), timeout=5.0)
    # Second call must be a no-op fast path
    await asyncio.wait_for(store.init(), timeout=1.0)
    row = await asyncio.wait_for(store.get_agent_execution("missing"), timeout=2.0)
    assert row is None


@pytest.mark.asyncio
async def test_init_source_releases_lock_before_prune():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[3]
        / "services/execution_store/_base.py"
    ).read_text(encoding="utf-8")
    assert "need_prune" in src
    assert "NEVER await prune()" in src
    # prune must not sit inside the same indented block as ``async with self._init_once_lock``
    # after ``self._inited = True`` without releasing — spot-check ordering.
    i_inited = src.index("self._inited = True")
    i_need = src.index("need_prune = bool(")
    i_prune_call = src.index("await self.prune()")
    assert i_inited < i_need < i_prune_call
