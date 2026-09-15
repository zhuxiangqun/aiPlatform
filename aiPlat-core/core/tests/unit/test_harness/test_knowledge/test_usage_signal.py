"""Tests for ActionStore usage-signal aggregation (S1–S4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.infrastructure.action_store import ActionStore


@pytest.fixture
async def store(tmp_path: Path):
    db = tmp_path / "execution_store.db"
    s = ActionStore(str(db))
    await s.initialize()
    return s


async def _insert(
    s: ActionStore,
    *,
    actor: str,
    status: str,
    created_at_sql: str = "datetime('now')",
    domain: str = "lock-service",
    action_id: str = "customer_action:lock-service:accept_order",
    entity_id: str = "wo-1",
):
    """created_at_sql is a SQLite datetime expression (trusted test-only)."""
    import aiosqlite
    import uuid

    async with aiosqlite.connect(s.db_path) as db:
        await db.execute(
            f"""
            INSERT INTO action_audit (
                audit_id, action_id, entity_id, domain_id,
                actor, result_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, {created_at_sql})
            """,
            (
                f"aud_{uuid.uuid4().hex[:12]}",
                action_id,
                entity_id,
                domain,
                actor,
                status,
            ),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_empty_returns_zeros(store):
    row = await store.query_usage_signal("lock-service")
    assert row["dau_today"] == 0
    assert row["calls_today"] == 0
    assert row["success_rate_today"] is None
    assert row["active_days_30d"] == 0
    assert row["status"] == "ok"


@pytest.mark.asyncio
async def test_dau_distinct_actors(store):
    await _insert(store, actor="alice", status="success")
    await _insert(store, actor="alice", status="executed")
    await _insert(store, actor="bob", status="success")
    row = await store.query_usage_signal("lock-service")
    assert row["dau_today"] == 2
    assert row["calls_today"] == 3


@pytest.mark.asyncio
async def test_success_rate_includes_executed(store):
    await _insert(store, actor="a", status="success")
    await _insert(store, actor="a", status="executed")
    await _insert(store, actor="b", status="failed")
    await _insert(store, actor="b", status="success")
    row = await store.query_usage_signal("lock-service")
    assert row["calls_today"] == 4
    assert row["success_rate_today"] == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_active_days_30d(store):
    await _insert(store, actor="a", status="success", created_at_sql="datetime('now')")
    await _insert(store, actor="a", status="success", created_at_sql="datetime('now', '-1 day')")
    await _insert(store, actor="a", status="success", created_at_sql="datetime('now', '-1 day', '+1 hour')")
    await _insert(store, actor="a", status="success", created_at_sql="datetime('now', '-5 days')")
    await _insert(store, actor="a", status="success", created_at_sql="datetime('now', '-40 days')")
    row = await store.query_usage_signal("lock-service")
    assert row["active_days_30d"] == 3


@pytest.mark.asyncio
async def test_domain_isolation(store):
    await _insert(store, actor="alice", status="success", domain="lock-service")
    await _insert(store, actor="bob", status="success", domain="service-domain")
    lock = await store.query_usage_signal("lock-service")
    svc = await store.query_usage_signal("service-domain")
    assert lock["dau_today"] == 1
    assert svc["dau_today"] == 1


@pytest.mark.asyncio
async def test_trend_and_days_validation(store):
    await _insert(store, actor="alice", status="success", created_at_sql="datetime('now')")
    await _insert(store, actor="bob", status="success", created_at_sql="datetime('now')")
    await _insert(store, actor="alice", status="failed", created_at_sql="datetime('now', '-1 day')")
    trend = await store.query_usage_trend("lock-service", days=30)
    assert len(trend) == 2
    with pytest.raises(ValueError):
        await store.query_usage_trend("lock-service", days=0)


@pytest.mark.asyncio
async def test_service_layer_with_injected_store(store):
    from core.apps.fde.service import usage_signal as us

    await _insert(store, actor="alice", status="success")
    out = await us.get_usage_signal("lock-service", store=store, require_domain=False)
    assert out["status"] == "ok"
    assert out["dau_today"] == 1
    assert "computed_at" in out

    empty = await us.get_usage_signal("", store=store, require_domain=False)
    assert empty["status"] == "unavailable"
