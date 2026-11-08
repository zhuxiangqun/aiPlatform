"""P1.2 freeze: reviewed → kind=frozen; claim_eligible stays false."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_factory import (
    generate_cases_from_template,
    publish_draft_workspace_pack,
)
from core.apps.eval.service.case_freeze import CaseFreezeError, freeze_workspace_pack
from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    write_pack_payload,
)
from core.apps.eval.service.case_review_queue import (
    enqueue_pack_for_review,
    submit_review_decision,
)


def _reviewed_pack(tmp_path, monkeypatch, pack_id="ws.freeze.demo", version="0.1.0"):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cases = generate_cases_from_template(
        {"prompt": "say ok", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "f1"}],
    )
    draft = publish_draft_workspace_pack(
        pack_id=pack_id,
        version=version,
        cases=cases,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    enqueue_pack_for_review(
        pack_id=pack_id, version=version, workspace_id="ws-a"
    )
    submit_review_decision(
        pack_id=pack_id,
        version=version,
        workspace_id="ws-a",
        decision="approve",
        reviewer="alice",
    )
    return draft


def test_freeze_reviewed_rehashes_kind(tmp_path, monkeypatch):
    draft = _reviewed_pack(tmp_path, monkeypatch)
    out = freeze_workspace_pack(
        pack_id="ws.freeze.demo",
        version="0.1.0",
        workspace_id="ws-a",
        frozen_by="alice",
    )
    assert out["ok"] is True
    assert out["kind"] == "frozen"
    assert out["status"] == "active"
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
    assert out["pack_hash"] != draft["pack_hash"]
    assert str(out["pack_hash"]).startswith("sha256:")
    # idempotent
    again = freeze_workspace_pack(
        pack_id="ws.freeze.demo", version="0.1.0", workspace_id="ws-a"
    )
    assert again.get("noop") is True
    assert again["pack_hash"] == out["pack_hash"]


def test_freeze_requires_reviewed(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cases = generate_cases_from_template(
        {"prompt": "x", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "c1"}],
    )
    publish_draft_workspace_pack(
        pack_id="ws.freeze.early",
        version="1.0.0",
        cases=cases,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    with pytest.raises(CaseFreezeError, match="reviewed"):
        freeze_workspace_pack(
            pack_id="ws.freeze.early", version="1.0.0", workspace_id="ws-a"
        )


def test_frozen_payload_immutable(tmp_path, monkeypatch):
    _reviewed_pack(tmp_path, monkeypatch, pack_id="ws.freeze.lock", version="2.0.0")
    freeze_workspace_pack(
        pack_id="ws.freeze.lock", version="2.0.0", workspace_id="ws-a"
    )
    with pytest.raises(PackRegistryError, match="refuse overwrite frozen"):
        write_pack_payload(
            pack_id="ws.freeze.lock",
            version="2.0.0",
            scope="workspace",
            cases=[{"case_id": "mutated", "prompt": "no", "rubric": {"type": "lexical"}, "category": "normal"}],
            meta={"kind": "frozen", "claim_eligible": False},
            workspace_id="ws-a",
            caller_workspace_id="ws-a",
        )
