"""W9 Scenario：模拟不写主事实；合并须人审。"""
from __future__ import annotations

import time

import pytest

from core.harness.knowledge_pipeline import scenario_branch as sb
from core.harness.knowledge_pipeline.fact_ledger import FactLedger


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "scenario.db")


@pytest.fixture()
async def ledger(tmp_path):
    fl = FactLedger(db_path=str(tmp_path / "facts.db"), raw_dir=tmp_path / "raw")
    await fl.initialize()
    return fl


@pytest.mark.asyncio
async def test_simulate_does_not_write_main_facts(db, ledger):
    created = sb.create_scenario(
        tenant_id="t1",
        branch="what-if-close",
        owner="u1",
        db_path=db,
    )
    assert created["status"] == "ok"
    sid = created["scenario_id"]

    before = await ledger.query_facts(tenant_id="t1", limit=100)
    out = sb.simulate_change(
        scenario_id=sid,
        tenant_id="t1",
        action="customer_action:lock-service:accept_order",
        target="O-1",
        params={"status": "accepted"},
        db_path=db,
    )
    assert out["status"] == "simulated"
    assert out["wrote_main_facts"] is False
    after = await ledger.query_facts(tenant_id="t1", limit=100)
    assert len(before) == len(after)

    got = sb.get_scenario(sid, tenant_id="t1", db_path=db)
    assert got and len(got["changes"]) == 1
    assert got["changes"][0]["status"] == "simulated"
    assert got["dry_run"] is True


def test_merge_requires_human_review(db):
    created = sb.create_scenario(
        tenant_id="t1", branch="br-1", owner="u1", db_path=db
    )
    sid = created["scenario_id"]
    sb.simulate_change(
        scenario_id=sid,
        tenant_id="t1",
        action="ticket.close",
        target="T-1",
        db_path=db,
    )
    # 为什么：未 pending_review 时直接 approve 必须拒绝
    denied = sb.approve_merge(
        scenario_id=sid, tenant_id="t1", approver="boss", db_path=db
    )
    assert denied["status"] == "invalid"
    assert denied["error"] == "not_pending_review"

    req = sb.request_merge(scenario_id=sid, tenant_id="t1", db_path=db)
    assert req["status"] == "pending_review"

    no_approver = sb.approve_merge(
        scenario_id=sid, tenant_id="t1", approver="", db_path=db
    )
    assert no_approver["error"] == "approver_required"

    ok = sb.approve_merge(
        scenario_id=sid, tenant_id="t1", approver="boss", db_path=db
    )
    assert ok["status"] == "merged"
    assert ok["wrote_main_facts"] is False
    assert ok["scenario"]["scenario_status"] == "merged"


def test_cross_tenant_lookup_hidden(db):
    created = sb.create_scenario(
        tenant_id="t1", branch="br-x", owner="u1", db_path=db
    )
    sid = created["scenario_id"]
    assert sb.get_scenario(sid, tenant_id="t2", db_path=db) is None


def test_expired_blocks_simulate(db):
    created = sb.create_scenario(
        tenant_id="t1",
        branch="br-exp",
        owner="u1",
        expires_at=time.time() - 10,
        db_path=db,
    )
    out = sb.simulate_change(
        scenario_id=created["scenario_id"],
        tenant_id="t1",
        action="ticket.close",
        target="T-1",
        db_path=db,
    )
    assert out["status"] == "expired"
