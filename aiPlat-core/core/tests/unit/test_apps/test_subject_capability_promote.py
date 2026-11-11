"""Subject capability bank promote (purpose_ok → freeze; claim closed)."""
from __future__ import annotations

from core.apps.eval.service.subject_capability_promote import (
    PROMOTE_SCHEMA,
    list_promotable_subject_kinds,
    promote_subject_capability_bank,
)


def test_list_promotable_includes_object_types_and_locals():
    kinds = list_promotable_subject_kinds()
    for k in (
        "agent",
        "prompt",
        "api",
        "dataset",
        "system",
        "kb",
        "tool",
        "multi_agent",
    ):
        assert k in kinds


def test_promote_prompt_capability_bank_freezes(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = promote_subject_capability_bank(
        subject_kind="prompt",
        workspace_id="ws-prompt",
        reviewer="owner",
        frozen_by="owner",
        notes="unit prompt promote",
    )
    assert out["schema"] == PROMOTE_SCHEMA
    assert out["ok"] is True
    assert out["subject_kind"] == "prompt"
    assert out["pack_id"] == "prompt.capability"
    assert out["kind"] == "frozen"
    assert out["status"] == "active"
    assert out["n_cases"] >= 15
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
    assert out["certification_eligible"] is False

    again = promote_subject_capability_bank(
        subject_kind="prompt", workspace_id="ws-prompt", reviewer="owner"
    )
    assert again.get("noop") is True or again["kind"] == "frozen"


def test_promote_agent_delegates_and_stays_claim_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = promote_subject_capability_bank(
        subject_kind="agent",
        workspace_id="ws-agent",
        reviewer="owner",
        frozen_by="owner",
    )
    assert out["ok"] is True
    assert out["subject_kind"] == "agent"
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False


def test_eval_promote_subject_capability_bank_facade(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.api.core_facade import (
        eval_list_promotable_subject_kinds,
        eval_promote_subject_capability_bank,
    )

    assert "dataset" in eval_list_promotable_subject_kinds()
    out = eval_promote_subject_capability_bank(
        subject_kind="dataset",
        workspace_id="ws-ds",
        reviewer="owner",
        frozen_by="owner",
    )
    assert out["ok"] is True
    assert out["pack_id"] == "dataset.capability"
    assert out["claim_eligible"] is False
