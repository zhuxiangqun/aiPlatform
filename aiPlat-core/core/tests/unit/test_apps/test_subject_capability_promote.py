"""Subject capability bank promote (purpose_ok → freeze; claim closed)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.apps.eval.service.api_capability_bank import (
    api_regression_status,
    default_seed_dir as api_default_seed_dir,
)
from core.apps.eval.service.subject_capability_promote import (
    PROMOTE_SCHEMA,
    SEED_PACK_FREEZE_SCHEMA,
    SEED_PURPOSE_OK_SCHEMA,
    SubjectCapabilityPromoteError,
    freeze_all_subject_seed_pack_meta,
    freeze_subject_seed_pack_meta,
    list_promotable_subject_kinds,
    promote_subject_capability_bank,
    stamp_all_subject_seed_purpose_ok,
    stamp_subject_seed_purpose_ok,
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
    assert out["content_purpose_ok"] is True

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


def test_stamp_subject_seed_purpose_ok_writes_review(tmp_path):
    import shutil

    src = api_default_seed_dir()
    assert src.is_dir(), f"missing api capability seed dir: {src}"
    dst = tmp_path / "api_capability"
    shutil.copytree(src, dst)
    out = stamp_subject_seed_purpose_ok(
        subject_kind="api", reviewer="owner", seed_dir=dst
    )
    assert out["schema"] == SEED_PURPOSE_OK_SCHEMA
    assert out["ok"] is True
    assert out["n_cases"] >= 15
    assert out["frozen"] is False
    assert out["claim_eligible"] is False
    sample = json.loads((dst / "cases" / "robustness.json").read_text())[0]
    assert sample["review"]["status"] == "purpose_ok"
    assert sample["review"]["reviewer"] == "owner"


def test_stamp_subject_seed_purpose_ok_rejects_agent():
    with pytest.raises(SubjectCapabilityPromoteError):
        stamp_subject_seed_purpose_ok(subject_kind="agent")


def test_stamp_all_and_api_regression_purpose_ok_progress():
    # Uses real workspace seeds (purpose_ok + pack.meta frozen in this PR).
    inv = stamp_all_subject_seed_purpose_ok(reviewer="owner")
    assert inv["ok"] is True
    assert inv["n_subjects"] >= 13
    assert inv["claim_eligible"] is False
    st = api_regression_status()
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["pack_status"] == "frozen"
    assert st["profile_complete"] is True
    assert st["claim_eligible"] is False


def test_freeze_subject_seed_pack_meta_writes_status(tmp_path):
    import shutil

    src = api_default_seed_dir()
    dst = tmp_path / "api_capability"
    shutil.copytree(src, dst)
    # Ensure draft before freeze (copy may already be frozen from seeds).
    meta_path = dst / "pack.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["status"] = "draft"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    out = freeze_subject_seed_pack_meta(
        subject_kind="api", reviewer="owner", seed_dir=dst
    )
    assert out["schema"] == SEED_PACK_FREEZE_SCHEMA
    assert out["ok"] is True
    assert out["frozen"] is True
    assert out["profile_complete"] is True
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
    written = json.loads(meta_path.read_text())
    assert written["status"] == "frozen"
    assert written["claim_eligible"] is False
    assert written["frozen_by"] == "owner"

    again = freeze_subject_seed_pack_meta(
        subject_kind="api", reviewer="owner", seed_dir=dst
    )
    assert again.get("noop") is True


def test_freeze_subject_seed_pack_meta_rejects_agent():
    with pytest.raises(SubjectCapabilityPromoteError):
        freeze_subject_seed_pack_meta(subject_kind="agent")


def test_freeze_all_and_api_regression_profile_complete():
    inv = freeze_all_subject_seed_pack_meta(reviewer="owner")
    assert inv["ok"] is True
    assert inv["n_subjects"] >= 13
    assert inv["claim_eligible"] is False
    st = api_regression_status()
    assert st["pack_status"] == "frozen"
    assert st["profile_complete"] is True
    assert st["claim_eligible"] is False
    assert "workspace promote optional" in st["next_action"]
