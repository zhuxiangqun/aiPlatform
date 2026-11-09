"""A1 intersection Track A/B — fixture blocked; scripted drill; rank_claim lock."""
from __future__ import annotations

import pytest

from core.apps.eval.service.a1_intersection_ops import (
    CLAIM_SENTENCE,
    a1_intersection_status_report,
    run_a1_intersection_compare,
    run_a1_intersection_track_a,
)
from core.apps.eval.service.mode_intersection_rank import list_rank_eligible_cases


@pytest.mark.asyncio
async def test_track_a_fixture_blocked_from_rank(tmp_path, monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_A1_ALLOW_SCRIPTED_WORKSPACE", raising=False)
    track = await run_a1_intersection_track_a(
        live=False,
        persist_dir=tmp_path,
        model_fingerprint="unit-model",
    )
    assert set(track["columns"]) == {"plan_execute", "conversational"}
    for mode, col in track["columns"].items():
        assert col["runtime_tier"] == "fixture", mode
    compare = run_a1_intersection_compare(
        mode_columns=track["columns"],
        min_n_per_capability=2,
    )
    assert compare["rank_claim"] is False
    assert compare["rank_claim_allowed"] is False
    assert compare["gate"]["ok"] is False


@pytest.mark.asyncio
async def test_track_a_scripted_workspace_drill(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_A1_ALLOW_SCRIPTED_WORKSPACE", "1")
    track = await run_a1_intersection_track_a(
        live=False,
        persist_dir=tmp_path,
        model_fingerprint="unit-model",
    )
    assert track["scripted_workspace_drill"] is True
    for mode, col in track["columns"].items():
        assert col["runtime_tier"] == "workspace_execute", mode
        assert col.get("rank_fingerprint")
    assert (tmp_path / "track_a.json").is_file()

    # Unsigned parity → allowed false even if engineering n ok
    compare = run_a1_intersection_compare(
        mode_columns=track["columns"],
        min_n_per_capability=2,
    )
    assert compare["rank_claim"] is False
    assert compare["rank_claim_allowed"] is False
    assert compare["claim_sentence_template"] == CLAIM_SENTENCE


@pytest.mark.asyncio
async def test_signed_unlocks_allowed_not_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_A1_ALLOW_SCRIPTED_WORKSPACE", "1")
    track = await run_a1_intersection_track_a(
        live=False,
        persist_dir=tmp_path,
        model_fingerprint="unit-model",
    )
    signoff = {
        "method_owner": "A",
        "engineering": "B",
        "independent_qa": "C",
        "status": "signed",
    }
    compare = run_a1_intersection_compare(
        mode_columns=track["columns"],
        signoff=signoff,
        min_n_per_capability=2,
    )
    assert compare["rank_claim"] is False
    # May still block if completion/sample fails; if gate ok then allowed true
    if compare["gate"]["ok"]:
        assert compare["rank_claim_allowed"] is True


def test_status_report_read_only():
    st = a1_intersection_status_report()
    assert st["schema"] == "eval.a1_intersection_status.v1"
    assert st["rank_claim"] is False
    assert st["accuracy_claim"] is False
    assert st["eligible_n"] >= 2
    assert list_rank_eligible_cases()
    assert "plan_execute" in st["modes_locked"]
