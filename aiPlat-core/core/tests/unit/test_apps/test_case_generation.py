"""P2.0 mutation / trace / holdout generation."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_factory import (
    generate_cases_from_template,
    publish_draft_workspace_pack,
)
from core.apps.eval.service.case_freeze import freeze_workspace_pack
from core.apps.eval.service.case_generation import (
    CaseGenerationError,
    apply_holdout_flags,
    cases_from_trace,
    mutate_cases,
    partition_holdout,
)
from core.apps.eval.service.case_pack_ops import (
    CasePackOpsError,
    build_mutation_draft_pack,
    build_trace_draft_pack,
    mark_pack_holdout,
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
