"""Suite Profile coverage heatmap + disclosure report."""
from __future__ import annotations

import pytest

from core.apps.eval.service.capability_id_map import V1_OUT_OF_SCOPE
from core.apps.eval.service.suite_profile_exam import run_suite_profile_exam
from core.apps.eval.service.suite_profile_report import (
    build_capability_heatmap,
    build_suite_profile_report,
)


def test_heatmap_lists_in_scope_and_unknown():
    heat = build_capability_heatmap(profile_id="agent.regression.v1")
    assert heat["ok"] is True
    assert heat["claim_eligible"] is False
    assert len(heat["rows"]) == 13  # v1.1 measurable subset
    assert heat["n_gaps"] == 0
    unknown_ids = {u["capability_id"] for u in heat["unknown_capabilities"]}
    assert unknown_ids == set(V1_OUT_OF_SCOPE)


@pytest.mark.asyncio
async def test_exam_embeds_report_with_disclosure():
    out = await run_suite_profile_exam(profile_id="agent.smoke.v1", live=False)
    report = out.get("report") or {}
    assert report.get("schema") == "eval.suite_profile_report.v1"
    disc = report.get("disclosure") or {}
    assert disc.get("profile_id") == "agent.smoke.v1"
    assert disc.get("manifest_hash")
    assert disc.get("execution_fingerprint")
    assert disc.get("claim_eligible") is False
    assert disc.get("accuracy_claim") is False
    heat = report.get("heatmap") or {}
    assert len(heat.get("rows") or []) == 13
    # smoke selected ≥1 per in-scope capability (session groups may add turns)
    assert sum(int(r.get("selected") or 0) for r in heat["rows"]) >= 13


def test_build_report_from_exam_dict():
    exam = {
        "ok": True,
        "profile_id": "agent.regression.v1",
        "live": False,
        "manifest_hash": "sha256:abc",
        "execution_fingerprint": "exec-xyz",
        "manifest_case_count": 2,
        "executed_case_count": 2,
        "counts": {"pass": 2, "fail": 0, "tasks": 2},
        "cases": [
            {"case_id": "a", "capability_id": "clarification", "status": "pass"},
            {"case_id": "b", "capability_id": "safety", "status": "fail"},
        ],
        "evaluation_plan": {
            "profile_id": "agent.regression.v1",
            "pack_ref": {"pack_id": "agent.capability", "version": "0.1.0"},
            "suite_profile": {"pack_id": "agent.capability", "pack_version": "0.1.0"},
            "counts": {"holdout": 0},
        },
    }
    report = build_suite_profile_report(exam)
    assert report["disclosure"]["pack_id"] == "agent.capability"
    assert report["disclosure"]["manifest_hash"] == "sha256:abc"
    heat_rows = {r["capability_id"]: r for r in report["heatmap"]["rows"]}
    assert heat_rows["clarification"]["pass"] == 1
    assert heat_rows["safety"]["fail"] == 1
    assert report["accuracy_claim"] is False
