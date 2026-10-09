"""Harness experiment factors + serial-chain recommendations."""

from __future__ import annotations

from pathlib import Path

from core.harness.evaluation.code_review_gold import load_gold_cases
from core.harness.evaluation.harness_factors import collect_harness_factors, harness_factors_delta
from core.harness.execution.meta_tool import meta_tool_auto_bind_enabled
from core.harness.meta.org_harness_metrics import serial_chain_recommendations


def test_collect_harness_factors_shape(monkeypatch):
    monkeypatch.setenv("AIPLAT_DONE_VERIFY", "true")
    monkeypatch.setenv("AIPLAT_META_TOOL_AUTO_BIND", "auto")
    f = collect_harness_factors(extra={"noise_profile": "balanced"})
    assert f["noise_profile"] == "balanced"
    assert "done_verify" in f
    assert "coding_policy_profile" in f


def test_harness_factors_delta():
    d = harness_factors_delta(
        {"done_verify": "true", "meta_tool_auto_bind": "on"},
        {"done_verify": "true", "meta_tool_auto_bind": "off"},
    )
    assert "meta_tool_auto_bind" in d
    assert "done_verify" not in d


def test_serial_recommendations_high_ratio():
    tips = serial_chain_recommendations({
        "avg_serial_ratio": 0.55,
        "approval_pending": 8,
        "avg_approval_latency_sec": 7200,
        "gold_regressing": True,
        "p0_miss_rate": 0.3,
    })
    actions = {t["action"] for t in tips}
    assert "redesign_hitl_chain" in actions
    assert "hold_model_upgrade" in actions


def test_meta_tool_auto_bind_production(monkeypatch):
    monkeypatch.delenv("AIPLAT_META_TOOL_AUTO_BIND", raising=False)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    # default auto → on
    assert meta_tool_auto_bind_enabled() is True
    monkeypatch.setenv("AIPLAT_PROFILE", "dev")
    monkeypatch.setenv("AIPLAT_META_TOOL_AUTO_BIND", "auto")
    assert meta_tool_auto_bind_enabled() is False


def test_batch_40_seed_loads():
    seed = (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
        / "batch_20_reviewbench.yaml"
    )
    assert seed.is_file()
    cases = load_gold_cases(str(seed.parent))
    # batch (40) + 2 singleton seeds (may overlap ids → ≥40 unique preferred)
    ids = {c.id for c in cases}
    assert len(cases) >= 40
    assert len(ids) >= 40
    assert "path_traversal_upload" in ids
    assert "zip_slip_extract" in ids
    assert "xxe_xml_parse" in ids
    assert "privilege_escalation_claim" in ids
