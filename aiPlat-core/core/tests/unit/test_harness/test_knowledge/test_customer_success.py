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
        for i, actor in enumerate(["alice", "bob"] * 6):  # 12 non-platform
            # 3 failures for a2; rest success so today success_rate stays high
            status = "failed" if i < 3 else "success"
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
                    status,
                ),
            )
        # extra successes to keep S3 ≥ 95% (3 fail / 60+ success)
        for i in range(50):
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
                    "alice" if i % 2 == 0 else "bob",
                    "success",
                ),
            )
        # platform noise should be ignored for A-group
        await db.execute(
            """
            INSERT INTO action_audit (
                audit_id, action_id, entity_id, domain_id, actor, result_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (f"aud_{uuid.uuid4().hex[:8]}", "a", "e1", "lock-service", "system", "success"),
        )
        await db.commit()

    save_metric_handover(
        "lock-service",
        {"status": "signed", "customer_contact": "alice, bob"},
        actor="t",
    )
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
    a1 = next(i for i in out["checklist"]["A"] if i["id"] == "a1")
    assert a1["done"] is True
    assert a1["value"] >= 10
    a2 = next(i for i in out["checklist"]["A"] if i["id"] == "a2")
    assert a2["done"] is True
    a3 = next(i for i in out["checklist"]["A"] if i["id"] == "a3")
    assert a3.get("na") is True
    a4 = next(i for i in out["checklist"]["A"] if i["id"] == "a4")
    assert a4["done"] is True
    assert out["groups"]["A_independence"]["ok"] is True


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


@pytest.mark.asyncio
async def test_domain_peers_across_domains(cs_home, tmp_path):
    from core.apps.fde.service.customer_success import (
        list_domain_peers,
        save_metric_handover,
    )
    from core.harness.infrastructure.action_store import ActionStore
    import aiosqlite
    import uuid

    store = ActionStore(str(tmp_path / "peers.db"))
    await store.initialize()
    async with aiosqlite.connect(store.db_path) as db:
        for domain, actor, status in (
            ("lock-service", "alice", "success"),
            ("lock-service", "bob", "success"),
            ("service-domain", "carol", "failed"),
            ("service-domain", "dave", "success"),
        ):
            await db.execute(
                """
                INSERT INTO action_audit (
                    audit_id, action_id, entity_id, domain_id, actor, result_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (f"aud_{uuid.uuid4().hex[:8]}", "a", "e", domain, actor, status),
            )
        await db.commit()

    save_metric_handover("lock-service", {"status": "signed"}, actor="t")
    out = await list_domain_peers(store=store, limit=10)
    assert out["status"] == "ok"
    assert out["unit"] == "domain_id"
    ids = {r["domain_id"] for r in out["peers"]}
    assert "lock-service" in ids
    assert "service-domain" in ids
    lock = next(r for r in out["peers"] if r["domain_id"] == "lock-service")
    assert lock["handover_status"] == "signed"
    assert lock["success_rate_today"] == pytest.approx(1.0)
    assert out["peer_baseline"]["domain_count"] == 2
    assert out["peer_baseline"]["median_success_rate"] is not None
