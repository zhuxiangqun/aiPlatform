"""OOS deep engineering packs + research refuse inventory."""
from __future__ import annotations

import pytest

from core.apps.eval.service.security_oos_deep import (
    ENGINEERING_ORDER,
    SecurityOosDeepError,
    build_research_refuse_inventory,
    evaluate_oos05_t11_fixture_gate,
    evaluate_oos_engineering_pack,
    list_engineering_oos_ids,
    load_oos_deep_packs,
    security_oos_deep_status,
)


def test_load_packs_and_order():
    packs = load_oos_deep_packs()
    assert packs["schema"] == "eval.security_oos_deep_packs.v1"
    assert packs["security_certification"] is False
    assert list_engineering_oos_ids(packs)[:4] == list(ENGINEERING_ORDER)


def test_oos07_incomplete_without_results():
    ev = evaluate_oos_engineering_pack("OOS-07")
    assert ev["fixture_ready"] is True
    assert ev["complete"] is False
    assert ev["covered"] is False
    assert ev["engineering_pass"] is False
    assert ev["claimable"] is False


def test_oos07_pass_still_not_covered():
    pack = load_oos_deep_packs()
    probes = pack["engineering_packs"]["OOS-07"]["probes"]
    results = {p["id"]: {"ok": True, "status": "fixture_pass"} for p in probes}
    ev = evaluate_oos_engineering_pack("OOS-07", probe_results=results)
    assert ev["complete"] is True
    assert ev["engineering_pass"] is True
    assert ev["covered"] is False
    assert ev["security_certification"] is False


def test_oos04_and_oos06_present():
    for oid in ("OOS-04", "OOS-06"):
        ev = evaluate_oos_engineering_pack(oid)
        assert ev["oos_id"] == oid
        assert ev["covered"] is False


def test_oos05_feeds_t11_fixture_count_but_not_graduate():
    gate = evaluate_oos05_t11_fixture_gate()
    assert gate["fixture_pack_ready"] is True
    assert gate["fixture_n"] >= 5
    checks = {c["id"]: c for c in gate["t11_gate"]["checks"]}
    assert checks["min_fixture_pack"]["ok"] is True
    assert gate["t11_gate"]["graduated"] is False
    assert gate["covered"] is False


def test_research_refuse_01_02_03():
    inv = build_research_refuse_inventory()
    ids = {c["oos_id"] for c in inv["research_refuse"]}
    assert ids == {"OOS-01", "OOS-02", "OOS-03"}
    assert all(c["score_as_text_asr"] is False for c in inv["research_refuse"])
    track = {c["oos_id"] for c in inv["track_excluded"]}
    assert "OOS-08" in track and "OOS-09" in track


def test_unknown_oos_raises():
    with pytest.raises(SecurityOosDeepError):
        evaluate_oos_engineering_pack("OOS-99")


def test_status_and_facade():
    st = security_oos_deep_status()
    assert st["slice"] == "OOS-DEEP"
    assert st["any_covered"] is False
    assert len(st["engineering"]) == 4
    assert st["security_certification"] is False

    from core.api.core_facade import (
        eval_build_research_refuse_inventory,
        eval_evaluate_oos_engineering_pack,
        eval_security_oos_deep_status,
    )

    assert eval_security_oos_deep_status()["ok"] is True
    assert eval_evaluate_oos_engineering_pack("OOS-07")["covered"] is False
    assert len(eval_build_research_refuse_inventory()["research_refuse"]) == 3
