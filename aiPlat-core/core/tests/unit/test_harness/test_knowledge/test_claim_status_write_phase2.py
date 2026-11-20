"""N03 deepen：Claim 状态写路径（put_claim + 审计）；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_claim_status_write_gate,
    run_claim_status_write_suite,
    transition_claim_status,
    transition_claim_status_pure,
)
from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.fact_state_machine import (
    FactStateMachineError,
    evaluate_claim_status_write_gate as core_gate,
    run_claim_status_write_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _seed_claim(ledger: FactLedger, *, status: str = "accepted"):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n03/status.txt",
        content=b"n03-status",
        connector="n03",
    )
    return await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text="door is locked",
        evidence=[
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": "ok",
                "fetched_at": src["fetched_at"],
            }
        ],
        source_policy="p1",
        extractor_version="t",
        review_status="published",
        confidence=0.8,
        status=status,
    )


@pytest.mark.asyncio
async def test_accepted_to_contested_persisted(ledger: FactLedger, tmp_path):
    claim = await _seed_claim(ledger)
    audit_db = str(tmp_path / "fact_state.sqlite3")
    mid = await transition_claim_status(
        claim_id=claim["claim_id"],
        tenant_id="t1",
        to_status="contested",
        actor="reviewer-1",
        reason="peer conflict",
        db_path=audit_db,
        ledger=ledger,
    )
    got = await ledger.get_claim(claim["claim_id"], tenant_id="t1")
    assert mid["claim"]["status"] == "contested"
    assert got is not None and got["status"] == "contested"
    assert int(mid["claim"]["revision"]) > int(claim["revision"])
    assert mid["transition"]["machine"] == "claim_status"


@pytest.mark.asyncio
async def test_illegal_edge_rejected(ledger: FactLedger, tmp_path):
    claim = await _seed_claim(ledger, status="archived")
    with pytest.raises(FactStateMachineError):
        await transition_claim_status(
            claim_id=claim["claim_id"],
            tenant_id="t1",
            to_status="accepted",
            actor="reviewer-1",
            reason="illegal reopen",
            db_path=str(tmp_path / "aud.sqlite3"),
            ledger=ledger,
        )


def test_pure_edge_still_available():
    # 诊断纯边路径仍可走；不写 Claim 表
    receipt = transition_claim_status_pure(
        claim_id="c-diag",
        tenant_id="t1",
        from_status="accepted",
        to_status="contested",
        actor="diag",
        reason="probe",
    )
    assert receipt["machine"] == "claim_status"
    assert receipt["to_state"] == "contested"


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 4
    assert suite["certified"] is False
    assert suite["n03_full_conformance"] is False
    gate = core_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    bad = dict(suite)
    bad["n03_full_conformance"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


@pytest.mark.asyncio
async def test_facade_suite_and_gate():
    suite = await run_claim_status_write_suite()
    assert suite["ok"] is True
    gate = evaluate_claim_status_write_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_docs_and_wiring_state():
    fsm = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "fact_state_machine.py"
    )
    text = fsm.read_text(encoding="utf-8")
    assert "async def transition_claim_status(" in text
    assert "run_claim_status_write_suite" in text
    assert "evaluate_claim_status_write_gate" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    fct = facade.read_text(encoding="utf-8")
    assert "async def transition_claim_status(" in fct
    assert "run_claim_status_write_suite" in fct
    route = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "fact_state_routes.py"
    )
    rtext = route.read_text(encoding="utf-8")
    assert "await transition_claim_status(" in rtext
    assert "from_status" not in rtext.split("ClaimTransitionBody")[1].split("class ")[0]
