"""P1 canonical honesty — Central legacy_7dim vs package engineering composite."""
from __future__ import annotations

from core.harness.evaluation.eval_runner import serialize_eval_result
from core.harness.evaluation.eval_types import AgentEvalResult


def test_agent_eval_result_marks_report_only_dims():
    r = AgentEvalResult(agent_id="a1", eval_set_id="s1")
    h = r.scoring_honesty()
    assert h["composite_policy"] == "legacy_7dim"
    assert h["accuracy_claim"] is False
    assert h["deprecated_for_engineering"] is True
    assert "text_quality" in h["report_only_dimensions"]
    assert "content_safety" in h["report_only_dimensions"]
    assert "refusal" in h["report_only_dimensions"]
    assert "task_completion" in h["scored_dimensions"]
    assert "text_quality" not in h["scored_dimensions"]
    assert h["canonical_engineering_composite"].endswith("scoring/composite.py")


def test_serialize_eval_result_embeds_scoring_honesty():
    r = AgentEvalResult(agent_id="a1", eval_set_id="s1", total_tasks=0)
    payload = serialize_eval_result(r)
    assert payload["accuracy_claim"] is False
    assert payload["scoring"]["composite_policy"] == "legacy_7dim"
    assert payload["scoring"]["accuracy_claim"] is False
    assert payload["scoring"]["deprecated_for_engineering"] is True
    assert "refusal" in payload["scoring"]["report_only_dimensions"]
    # Formula unchanged: empty dims still produce a finite legacy score.
    assert isinstance(payload["composite_score"], (int, float))
