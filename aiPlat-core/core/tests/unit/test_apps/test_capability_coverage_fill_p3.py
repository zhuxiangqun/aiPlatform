"""P3 coverage-driven fill — gap analyze + mutation candidates + expand."""
from __future__ import annotations

import pytest

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PACK_VERSION,
    build_agent_capability_cases,
    promote_agent_capability_bank,
)
from core.apps.eval.service.capability_coverage_fill import (
    CapabilityCoverageFillError,
    analyze_capability_coverage,
    fill_capability_coverage,
    generate_coverage_fill_candidates,
)
from core.apps.eval.service.case_factory import publish_draft_workspace_pack


def test_analyze_regression_quotas_no_gap():
    report = analyze_capability_coverage()
    assert report["ok"] is True
    assert report["claim_eligible"] is False
    assert report["n_gaps"] == 0
    assert report["covered_capabilities"] == report["total_in_scope"]


def test_analyze_benchmark_min8_no_gap():
    report = analyze_capability_coverage(min_per_capability=8)
    assert report["n_gaps"] == 0
    for g in report["gaps"]:
        assert g["need"] == 8
        assert g["have"] >= 8
        assert g["gap"] == 0


def _one_per_in_scope_bank():
    """One seed per in-scope capability so mutation fill has parents + gaps."""
    seen = set()
    out = []
    for c in build_agent_capability_cases():
        cap = c["capabilities"][0]
        if cap in seen:
            continue
        seen.add(cap)
        out.append(c)
        if len(out) >= 8:
            break
    return out


def test_generate_mutation_candidates_for_thin_bank():
    thin = _one_per_in_scope_bank()
    out = generate_coverage_fill_candidates(
        cases=thin, min_per_capability=8, method="mutation", seed="42"
    )
    assert out["ok"] is True
    assert out["n_candidates"] > 0
    assert out["claim_eligible"] is False
    for c in out["candidates"]:
        assert "coverage_fill" in (c.get("tags") or [])
        assert (c.get("review") or {}).get("status") == "draft"
        assert c.get("capabilities")


def test_fill_dry_full_bank_noop_candidates():
    out = fill_capability_coverage(
        workspace_id="ws-fill",
        min_per_capability=8,
        apply=False,
    )
    assert out["applied"] is False
    assert out["n_candidates"] == 0
    assert out["claim_eligible"] is False


def test_fill_dry_thin_bank_proposes_candidates():
    thin = _one_per_in_scope_bank()
    out = fill_capability_coverage(
        workspace_id="ws-fill",
        min_per_capability=8,
        apply=False,
        cases=thin,
    )
    assert out["applied"] is False
    assert out["n_candidates"] > 0


def test_fill_apply_expands_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    # Publish a thin draft that we can expand (not the frozen promote path).
    seeds = build_agent_capability_cases()[:2]
    publish_draft_workspace_pack(
        pack_id="ws.fill.demo",
        version="0.1.0",
        cases=seeds,
        workspace_id="ws-fill",
        caller_workspace_id="ws-fill",
    )
    out = fill_capability_coverage(
        workspace_id="ws-fill",
        pack_id="ws.fill.demo",
        version="0.1.0",
        min_per_capability=8,
        method="mutation",
        apply=True,
        cases=seeds,  # gaps computed against thin set
    )
    assert out["applied"] is True
    assert int(out.get("added") or 0) > 0
    assert out["claim_eligible"] is False


def test_fill_apply_rejects_frozen(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    promote_agent_capability_bank(
        workspace_id="ws-fz", reviewer="owner", frozen_by="owner"
    )
    # Force gaps against a thin view so apply attempts expand on frozen pack.
    with pytest.raises(CapabilityCoverageFillError, match="frozen|immutable|bump"):
        fill_capability_coverage(
            workspace_id="ws-fz",
            pack_id=PACK_ID,
            version=PACK_VERSION,
            min_per_capability=8,
            apply=True,
            cases=_one_per_in_scope_bank(),
        )
