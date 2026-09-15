"""Tests for customer-success handover + escort exit."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def cs_home(tmp_path: Path, monkeypatch):
    home = tmp_path / "aiplat_home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    return home


def test_metric_handover_roundtrip(cs_home):
    from core.apps.fde.service.customer_success import get_metric_handover, save_metric_handover

    d = get_metric_handover("lock-service")
    assert d["status"] == "draft"
    assert d["domain_id"] == "lock-service"
    saved = save_metric_handover(
        "lock-service",
        {"status": "signed", "fde_owner": "oliver", "customer_contact": "alice"},
        actor="test",
    )
    assert saved["status"] == "signed"
    assert get_metric_handover("lock-service")["fde_owner"] == "oliver"
    assert (cs_home / "fde_customer_success" / "handover_lock-service.json").exists()


def test_escort_exit_checklist_and_groups(cs_home):
    from core.apps.fde.service.customer_success import get_escort_exit, save_escort_exit

    cur = get_escort_exit("lock-service")
    assert cur["status"] == "evaluating"
    items_a = [dict(i, done=True) for i in cur["checklist"]["A"]]
    items_b = [dict(i, done=True) for i in cur["checklist"]["B"]]
    items_c = [dict(i, done=True) for i in cur["checklist"]["C"]]
    items_d = [dict(i, done=True) for i in cur["checklist"]["D"]]
    out = save_escort_exit(
        "lock-service",
        {"checklist": {"A": items_a, "B": items_b, "C": items_c, "D": items_d}},
        actor="test",
    )
    assert out["groups"]["A_independence"]["ok"] is True
    assert out["status"] == "can_exit"


@pytest.mark.asyncio
async def test_evaluate_escort_from_usage(cs_home, tmp_path):
    from core.apps.fde.service.customer_success import (
        evaluate_escort_exit_from_signals,
        save_metric_handover,
    )
    from core.harness.infrastructure.action_store import ActionStore
    import aiosqlite
    import uuid

    store = ActionStore(str(tmp_path / "exec.db"))
    await store.initialize()
    async with aiosqlite.connect(store.db_path) as db:
        for actor in ("alice", "bob"):
            await db.execute(
                """
                INSERT INTO action_audit (
                    audit_id, action_id, entity_id, domain_id, actor, result_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    f"aud_{uuid.uuid4().hex[:8]}",
                    "customer_action:lock-service:accept_order",
                    "e1",
                    "lock-service",
                    actor,
                    "success",
                ),
            )
        await db.commit()

    save_metric_handover("lock-service", {"status": "signed"}, actor="t")
    out = await evaluate_escort_exit_from_signals(
        "lock-service",
        actor="t",
        quality_score=80,
        canary_ok=True,
        store=store,
    )
    c1 = next(i for i in out["checklist"]["C"] if i["id"] == "c1")
    assert c1["done"] is True
    d1 = next(i for i in out["checklist"]["D"] if i["id"] == "d1")
    assert d1["done"] is True
    b2 = next(i for i in out["checklist"]["B"] if i["id"] == "b2")
    assert b2["done"] is True
    b1 = next(i for i in out["checklist"]["B"] if i["id"] == "b1")
    assert b1["done"] is True


@pytest.mark.asyncio
async def test_usage_baseline_capture(tmp_path):
    from core.harness.infrastructure.action_store import ActionStore
    import aiosqlite
    import uuid

    store = ActionStore(str(tmp_path / "b.db"))
    await store.initialize()
    async with aiosqlite.connect(store.db_path) as db:
        for day in (0, 1, 2):
            await db.execute(
                f"""
                INSERT INTO action_audit (
                    audit_id, action_id, entity_id, domain_id, actor, result_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-{day} days'))
                """,
                (f"aud_{uuid.uuid4().hex[:8]}", "a", "e", "lock-service", "alice", "success"),
            )
        await db.commit()
    row = await store.capture_usage_baseline_from_trend("lock-service", days=30, captured_by="t")
    assert row["baseline_active_days"] == 3
    got = await store.get_usage_baseline("lock-service")
    assert got is not None
    assert got["captured_by"] == "t"
