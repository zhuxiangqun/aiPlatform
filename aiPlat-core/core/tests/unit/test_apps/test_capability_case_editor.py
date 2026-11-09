"""Capability Case Editor — seed browse + workspace draft upsert/delete."""
from __future__ import annotations

import pytest

from core.apps.eval.service.capability_case_bank import PACK_ID, PACK_VERSION
from core.apps.eval.service.capability_case_editor import (
    CapabilityCaseEditorError,
    delete_workspace_pack_case,
    get_seed_capability_case,
    list_seed_capability_cases,
    list_workspace_pack_cases,
    open_capability_bank_editor,
    upsert_workspace_pack_case,
)
from core.apps.eval.service.capability_case_bank import promote_agent_capability_bank


def test_list_seed_cases_readonly():
    out = list_seed_capability_cases()
    assert out["ok"] is True
    assert out["editable"] is False
    assert out["n_cases"] >= 64
    assert out["claim_eligible"] is False


def test_get_seed_case():
    out = get_seed_capability_case(case_id="agent.clarification.001")
    assert out["ok"] is True
    assert out["case"]["case_id"] == "agent.clarification.001"
    assert out["editable"] is False


def test_open_editor_publishes_seed_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    opened = open_capability_bank_editor(workspace_id="ws-ed")
    assert opened["ok"] is True
    assert opened["editable"] is True
    assert opened["action"] == "published_seed_draft"
    listed = list_workspace_pack_cases(
        workspace_id="ws-ed", pack_id=PACK_ID, version=PACK_VERSION
    )
    assert listed["n_cases"] >= 64
    assert listed["editable"] is True


def test_upsert_and_delete_draft_case(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    open_capability_bank_editor(workspace_id="ws-ed2")
    case = get_seed_capability_case(case_id="agent.clarification.001")["case"]
    case["case_id"] = "agent.clarification.ui001"
    case["prompt"] = "请澄清这个模糊需求。"
    up = upsert_workspace_pack_case(
        workspace_id="ws-ed2",
        case=case,
        pack_id=PACK_ID,
        version=PACK_VERSION,
    )
    assert up["created"] is True
    assert up["claim_eligible"] is False
    listed = list_workspace_pack_cases(workspace_id="ws-ed2")
    n0 = listed["n_cases"]
    assert n0 >= 65
    deleted = delete_workspace_pack_case(
        workspace_id="ws-ed2",
        case_id="agent.clarification.ui001",
    )
    assert deleted["deleted"] is True
    listed2 = list_workspace_pack_cases(workspace_id="ws-ed2")
    assert listed2["n_cases"] == n0 - 1


def test_frozen_requires_bump(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    promote_agent_capability_bank(
        workspace_id="ws-fz", reviewer="owner", frozen_by="owner"
    )
    with pytest.raises(CapabilityCaseEditorError, match="frozen|immutable"):
        upsert_workspace_pack_case(
            workspace_id="ws-fz",
            case=get_seed_capability_case(case_id="agent.clarification.001")["case"],
        )
    opened = open_capability_bank_editor(
        workspace_id="ws-fz", bump_if_frozen=True
    )
    assert opened["action"] == "bumped_frozen"
    assert opened["editable"] is True
    assert opened["version"] != PACK_VERSION
