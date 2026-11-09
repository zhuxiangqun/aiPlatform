"""SEC-P2a: S1→Facade + OOS/untested family auto-list."""
from __future__ import annotations

from core.apps.eval.service.security_s1_disclosure import (
    build_untested_oos_disclosure,
    load_s1_aggregate_evidence,
    load_s1_live_attack_pack,
    security_sec_p2a_status,
    summarize_s1_pack,
)


def test_s1_pack_loads_min_20():
    pack = load_s1_live_attack_pack()
    assert pack["schema"] == "eval.s1.live_attack_pack.v0"
    assert pack.get("accuracy_claim") is False
    assert len(pack["cases"]) >= 20
    summary = summarize_s1_pack(pack)
    assert summary["n_cases"] >= 20
    assert "T01" in summary["mapped_threat_families"]
    assert "T02" in summary["mapped_threat_families"]
    assert summary["live_skill_tools"] is False


def test_aggregate_optional_honesty():
    agg = load_s1_aggregate_evidence()
    # Evidence file exists in repo; if present must stay claim-closed
    if agg is not None:
        assert agg.get("accuracy_claim") is False
        assert agg.get("asr") is not None


def test_oos_disclosure_lists_c15_sets():
    disc = build_untested_oos_disclosure(by_case={})
    assert disc["schema"] == "eval.security_untested_oos_disclosure.v1"
    assert "OOS-01" in disc["oos_ids"]
    assert len(disc["out_of_scope"]) >= 9
    assert disc["untested_threat_families"]  # empty by_case → all untested
    assert disc["l5_declare_allowed_families"] == []
    assert disc["accuracy_claim"] is False
    assert disc["security_certification"] is False


def test_p2a_status_card():
    st = security_sec_p2a_status()
    assert st["schema"] == "eval.security_sec_p2a_status.v1"
    assert st["slice"] == "SEC-P2a"
    assert st["s1_pack"]["n_cases"] >= 20
    assert st["s1_pack"]["live_skill_tools"] is False
    assert st["disclosure"]["oos_ids"]
    assert st["accuracy_claim"] is False
    assert st["security_certification"] is False
    assert st["claim_eligible"] is False
    # annotation-only S1 hits still leave most families below min_n / untested
    assert st["disclosure"]["annotation_only"] is True
