"""P2.0 mutation / trace / holdout + P3.0 LLM candidates / difficulty / judge ticket."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_factory import (
    generate_cases_from_template,
    publish_draft_workspace_pack,
)
from core.apps.eval.service.case_freeze import freeze_workspace_pack
from core.apps.eval.service.case_calibration import compute_rating_agreement
from core.apps.eval.service.case_generation import (
    CaseGenerationError,
    apply_holdout_flags,
    build_judge_calibration_ticket,
    cases_from_trace,
    generate_llm_candidate_cases,
    mutate_cases,
    partition_holdout,
    propose_difficulty,
)
from core.apps.eval.service.case_pack_ops import (
    CasePackOpsError,
    build_llm_candidate_draft_pack,
    build_mutation_draft_pack,
    build_trace_draft_pack,
    calibrate_pack_difficulty,
    close_judge_calibration_ticket_for_pack,
    mark_pack_holdout,
    open_judge_calibration_ticket_for_pack,
    propose_pack_difficulty,
    record_judge_calibration_ratings_for_pack,
)
from core.apps.eval.service.case_review_queue import (
    enqueue_pack_for_review,
    submit_review_decision,
)


def test_mutate_deterministic():
    seeds = [
        {
            "case_id": "s1",
            "prompt": "Hello, world!",
            "rubric": {"type": "lexical", "must_contain": ["ok"]},
            "category": "normal",
        }
    ]
    a = mutate_cases(seeds, ops=["append_noise", "drop_punctuation"], seed="42")
    b = mutate_cases(seeds, ops=["append_noise", "drop_punctuation"], seed="42")
    assert len(a) == 2
    assert [c["case_id"] for c in a] == [c["case_id"] for c in b]
    assert [c["prompt"] for c in a] == [c["prompt"] for c in b]
    assert all(c["provenance"]["generator"] == "case_mutation" for c in a)


def test_cases_from_trace_and_holdout_partition():
    cases = cases_from_trace(
        {
            "messages": [{"role": "user", "content": "open the door"}],
            "tool_calls": [{"name": "unlock"}],
            "must_contain": ["door"],
        }
    )
    assert len(cases) == 1
    assert cases[0]["expected_tools"] == ["unlock"]
    assert cases[0]["provenance"]["generator"] == "case_trace"
    flagged = apply_holdout_flags(cases, case_ids=[cases[0]["case_id"]], holdout=True)
    parts = partition_holdout(flagged)
    assert parts["n_holdout"] == 1
    assert parts["n_eval"] == 0


def test_publish_mutation_and_trace_packs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    seeds = generate_cases_from_template(
        {"prompt": "base", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "b1"}],
    )
    mut = build_mutation_draft_pack(
        pack_id="ws.gen.mut",
        version="0.1.0",
        workspace_id="ws-a",
        seed_cases=seeds,
        ops=["append_noise"],
        seed="7",
    )
    assert mut["ok"] is True
    assert mut["kind"] == "generated"
    assert mut["claim_eligible"] is False
    tr = build_trace_draft_pack(
        pack_id="ws.gen.tr",
        version="0.1.0",
        workspace_id="ws-a",
        traces=[{"prompt": "from run", "tool_calls": [{"name": "search"}]}],
    )
    assert tr["kind"] == "trace"
    assert tr["claim_eligible"] is False


def test_mark_holdout_and_freeze_generated_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    seeds = generate_cases_from_template(
        {"prompt": "a", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "h1"}, {"case_id": "h2"}],
    )
    publish_draft_workspace_pack(
        pack_id="ws.gen.ho",
        version="0.1.0",
        cases=seeds,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    marked = mark_pack_holdout(
        pack_id="ws.gen.ho",
        version="0.1.0",
        workspace_id="ws-a",
        ratio=0.5,
        seed="1",
    )
    assert marked["n_holdout"] == 1
    assert marked["claim_eligible"] is False

    mut = build_mutation_draft_pack(
        pack_id="ws.gen.nofreeze",
        version="1.0.0",
        workspace_id="ws-a",
        seed_cases=seeds[:1],
        ops=["case_swap"],
        seed="1",
    )
    enqueue_pack_for_review(
        pack_id="ws.gen.nofreeze", version="1.0.0", workspace_id="ws-a"
    )
    submit_review_decision(
        pack_id="ws.gen.nofreeze",
        version="1.0.0",
        workspace_id="ws-a",
        decision="approve",
    )
    with pytest.raises(Exception, match="cannot freeze kind"):
        freeze_workspace_pack(
            pack_id="ws.gen.nofreeze", version="1.0.0", workspace_id="ws-a"
        )


def test_unknown_mutation_rejected():
    with pytest.raises(CaseGenerationError, match="unsupported"):
        mutate_cases(
            [{"case_id": "x", "prompt": "p", "rubric": {"type": "lexical"}, "category": "normal"}],
            ops=["llm_rewrite"],
        )


@pytest.mark.asyncio
async def test_llm_candidates_dry_and_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cases = await generate_llm_candidate_cases(
        theme="unlock door", n=2, seed="s1", dry=True
    )
    assert len(cases) == 2
    assert all(c["provenance"]["generator"] == "case_llm" for c in cases)
    assert all("llm_candidate" in (c.get("tags") or []) for c in cases)

    async def fake_llm(_prompt: str) -> str:
        return (
            '[{"case_id":"c1","prompt":"p1","rubric":{"type":"lexical",'
            '"must_contain":["ok"]},"category":"normal"}]'
        )

    injected = await generate_llm_candidate_cases(
        theme="t", n=1, seed="i", llm_generate_fn=fake_llm
    )
    assert injected[0]["case_id"] == "c1"

    pub = await build_llm_candidate_draft_pack(
        pack_id="ws.gen.llm",
        version="0.1.0",
        workspace_id="ws-a",
        theme="smoke",
        n=2,
        seed="9",
        dry=True,
    )
    assert pub["ok"] is True
    assert pub["kind"] == "generated"
    assert pub["claim_eligible"] is False
    assert pub["generator"] == "case_llm"


def test_propose_difficulty_and_judge_ticket(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    seeds = generate_cases_from_template(
        {"prompt": "short", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "d1"}, {"case_id": "d2", "prompt": "x" * 250}],
    )
    labeled = propose_difficulty(seeds)
    assert labeled[0]["difficulty"] in ("easy", "medium", "hard")
    assert labeled[0]["difficulty_proposal"]["calibrated"] is False

    publish_draft_workspace_pack(
        pack_id="ws.gen.diff",
        version="0.1.0",
        cases=seeds,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    prop = propose_pack_difficulty(
        pack_id="ws.gen.diff",
        version="0.1.0",
        workspace_id="ws-a",
        persist=True,
    )
    assert prop["ok"] is True
    assert prop["persisted"] is True
    assert prop["accuracy_claim"] is False

    ticket = build_judge_calibration_ticket(
        pack_id="ws.gen.diff", version="0.1.0", notes="unit"
    )
    assert ticket["claim_eligible"] is False
    assert ticket["ticket_kind"] == "judge_calibration"
    opened = open_judge_calibration_ticket_for_pack(
        pack_id="ws.gen.diff",
        version="0.1.0",
        workspace_id="ws-a",
        notes="ops",
        sample_case_ids=["d1"],
    )
    assert opened["workspace_id"] == "ws-a"
    assert opened.get("ticket_id")
    rated = record_judge_calibration_ratings_for_pack(
        workspace_id="ws-a",
        ticket_id=opened["ticket_id"],
        ratings=[
            {"case_id": "d1", "score": 1, "rater": "a"},
            {"case_id": "d1", "score": 1, "rater": "b"},
        ],
    )
    assert rated["status"] == "in_progress"
    assert rated["agreement"]["agreement"] == 1.0
    closed = close_judge_calibration_ticket_for_pack(
        workspace_id="ws-a", ticket_id=opened["ticket_id"]
    )
    assert closed["status"] == "closed"
    assert closed["calibrated"] is True
    assert closed["accuracy_claim"] is False

    cal = calibrate_pack_difficulty(
        pack_id="ws.gen.diff",
        version="0.1.0",
        workspace_id="ws-a",
        labels=[{"case_id": "d1", "difficulty": "hard"}],
        rater="unit",
    )
    assert cal["calibrated"] is True
    assert cal["accuracy_claim"] is False
    assert cal["n_labeled"] >= 1

    agr = compute_rating_agreement(
        [{"case_id": "x", "score": 0}, {"case_id": "x", "score": 1}]
    )
    assert agr["agreement"] == 0.0
    with pytest.raises(CasePackOpsError):
        open_judge_calibration_ticket_for_pack(
            pack_id="", version="0.1.0", workspace_id="ws-a"
        )
