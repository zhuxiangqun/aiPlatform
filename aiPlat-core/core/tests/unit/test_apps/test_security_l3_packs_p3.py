"""SEC-P3: S-Tool/S-RAG L3 packs + A7 parity."""
from __future__ import annotations

import pytest

from core.apps.eval.service.security_l3_packs import (
    L3_FAMILIES,
    SecurityL3PacksError,
    evaluate_a7_l3_parity,
    evaluate_l3_case_fixture,
    load_l3_s_tool_s_rag_pack,
    run_l3_pack_fixtures,
    security_sec_p3_status,
)


def test_pack_loads_l3_only():
    pack = load_l3_s_tool_s_rag_pack()
    assert pack["schema"] == "eval.security_l3_s_tool_s_rag.v1"
    assert pack["eval_layer"] == "L3"
    assert pack["accuracy_claim"] is False
    assert "S-Tool" in pack["packs"] and "S-RAG" in pack["packs"]
    tids = set()
    for c in pack["cases"]:
        assert c["eval_layer"] == "L3"
        assert c["oracle"] == "tool_trace"
        tids.update(c["threat_ids"])
    assert L3_FAMILIES <= tids


def test_fixture_run_all_pass_fixture_only():
    run = run_l3_pack_fixtures()
    assert run["coverage"] == "exercised_fixture"
    assert run["live_destructive_execution"] is False
    assert run["isolation_covered"] is False
    assert run["n_fail"] == 0
    assert run["n_pass"] == run["n_cases"]
    assert run["accuracy_claim"] is False


def test_side_effect_detector():
    bad = evaluate_l3_case_fixture(
        {
            "case_id": "x",
            "pack": "S-Tool",
            "threat_ids": ["T05-exec"],
            "expect": "deny_or_no_effect",
            "fixture_tool_trace": [{"name": "rm", "side_effect": "delete"}],
        }
    )
    assert bad["ok"] is False
    assert bad["attack_success"] is True

    detect = evaluate_l3_case_fixture(
        {
            "case_id": "y",
            "pack": "S-Tool",
            "threat_ids": ["T05-exec"],
            "expect": "detect_side_effect",
            "fixture_tool_trace": [{"name": "rm", "side_effect": "delete"}],
        }
    )
    assert detect["ok"] is True


def test_a7_parity_ok():
    parity = evaluate_a7_l3_parity()
    assert parity["ok"] is True, parity["errors"]
    assert parity["a7_covers_l3_exec"] is False
    assert set(parity["l3_threat_families"]) >= L3_FAMILIES


def test_a7_parity_flags_l1_exec_hosting():
    parity = evaluate_a7_l3_parity(
        l1_cases=[
            {
                "case_id": "bad",
                "eval_layer": "L1",
                "threat_ids": ["T05-exec"],
            }
        ]
    )
    assert parity["ok"] is False
    assert any("l1_hosts_l3_family" in e or "l1_layer_l3_threat" in e for e in parity["errors"])


def test_rejects_non_l3_pack(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(
        '{"schema":"eval.security_l3_s_tool_s_rag.v1","eval_layer":"L1",'
        '"packs":{"S-Tool":{},"S-RAG":{}},"cases":[]}',
        encoding="utf-8",
    )
    with pytest.raises(SecurityL3PacksError):
        load_l3_s_tool_s_rag_pack(path=p)


def test_p3_status_card():
    st = security_sec_p3_status()
    assert st["schema"] == "eval.security_sec_p3_status.v1"
    assert st["slice"] == "SEC-P3"
    assert st["ok"] is True
    assert st["a7_parity"]["ok"] is True
    assert st["live_destructive_execution"] is False
    assert st["security_certification"] is False
