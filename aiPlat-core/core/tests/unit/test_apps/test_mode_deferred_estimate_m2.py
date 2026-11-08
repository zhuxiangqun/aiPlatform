"""M2 deferred estimate — runtime_parts gate; deferred≠unknown; no live."""
from __future__ import annotations

import pytest

from core.apps.eval.service.mode_deferred_estimate import (
    ModeDeferredEstimateError,
    assert_m2_not_live,
    estimate_m2_deferred_modes,
    load_m2_deferred_estimate,
    validate_runtime_parts,
)


def test_load_m2_estimate():
    est = load_m2_deferred_estimate()
    assert est["schema"] == "eval.m2_deferred_estimate.v1"
    assert set(est["deferred_modes"]) >= {"multi_agent", "pipeline", "operator"}
    assert est["gate"]["live_exam_allowed"] is False


def test_estimate_report_aligned():
    out = estimate_m2_deferred_modes()
    assert out["ok"] is True, out
    assert out["phase"] == "m2"
    assert out["rank_claim"] is False
    assert out["gate"]["live_exam_allowed"] is False
    assert out["resolve_sample"]["neq_unknown"] is True
    assert out["total_engineering_days_est"] >= 3
    assert "multi_agent" in out["deferred_modes"]
    assert out["deferred_modes"]["multi_agent"]["neq_unknown"] is True


def test_validate_runtime_parts_missing():
    r = validate_runtime_parts([], mode="multi_agent")
    assert r["ok"] is False
    assert "runtime_parts_empty" in r["errors"]


def test_validate_runtime_parts_ok_shape():
    parts = [
        {
            "part_id": "coordinator",
            "sub_id": "c1",
            "runtime_tier": "workspace_execute",
            "target_runtime": "agent",
            "role": "coordinator",
        },
        {
            "part_id": "worker",
            "sub_id": "w1",
            "runtime_tier": "fixture",
            "target_runtime": "agent",
            "worker_id": "w-a",
        },
        {
            "part_id": "aggregate",
            "sub_id": "a1",
            "runtime_tier": "workspace_execute",
            "merge_policy": "vote",
        },
    ]
    r = validate_runtime_parts(parts, mode="multi_agent")
    assert r["ok"] is True, r


def test_assert_m2_not_live():
    with pytest.raises(ModeDeferredEstimateError, match="m2_live_forbidden"):
        assert_m2_not_live("multi_agent")
    assert_m2_not_live("react")  # no raise
