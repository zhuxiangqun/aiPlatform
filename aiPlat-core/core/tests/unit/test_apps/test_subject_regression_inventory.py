"""Cross-Subject regression honesty inventory."""
from __future__ import annotations

from core.apps.eval.service.subject_regression_inventory import (
    INVENTORY_SCHEMA,
    subject_regression_inventory,
)
from core.apps.eval.service.target_contract import OBJECT_TYPES


def test_inventory_covers_object_types_and_stays_claim_closed():
    inv = subject_regression_inventory()
    assert inv["schema"] == INVENTORY_SCHEMA
    assert inv["claim_eligible"] is False
    assert inv["accuracy_claim"] is False
    assert inv["certification_eligible"] is False
    assert inv["profile_complete_count"] == inv["subject_count"]
    assert inv["subject_count"] >= 14
    assert inv["object_type_subject_count"] == len(OBJECT_TYPES)

    by_kind = {r["subject_kind"]: r for r in inv["subjects"]}
    for ot in OBJECT_TYPES:
        assert ot in by_kind, ot
        row = by_kind[ot]
        assert row["object_type_member"] is True
        assert row["claim_eligible"] is False
        assert row["profile_complete"] is True
        assert row["ok"] is True, row
        assert row["quota_inventory_ok"] is True, row


def test_inventory_includes_subject_local_kinds():
    inv = subject_regression_inventory()
    kinds = {r["subject_kind"] for r in inv["subjects"]}
    for k in ("kb", "code_review", "session", "tool", "multi_agent"):
        assert k in kinds
        row = next(r for r in inv["subjects"] if r["subject_kind"] == k)
        assert row["object_type_member"] is False
        assert row["ok"] is True, row


def test_eval_subject_regression_inventory_facade():
    from core.api.core_facade import eval_subject_regression_inventory

    inv = eval_subject_regression_inventory()
    assert inv["schema"] == INVENTORY_SCHEMA
    assert inv["claim_eligible"] is False
    assert inv["quota_inventory_ok_count"] == inv["subject_count"]
    assert inv.get("workspace_promoted_count") == 0
    assert inv.get("workspace_id") == ""


def test_inventory_workspace_promote_enrichment(tmp_path, monkeypatch):
    """When workspace_id set, rows expose workspace_promoted (claim stays false)."""
    from core.apps.eval.service import case_pack_registry as reg
    from core.apps.eval.service.subject_capability_promote import _bank_specs
    from core.apps.eval.service.subject_regression_inventory import (
        subject_regression_inventory,
    )

    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    wid = "ws-inv-promote"
    spec = _bank_specs()["prompt"]
    pid = str(spec["pack_id"])
    ver = str(spec["version"])
    ph = "sha256:" + ("ab" * 32)
    reg.register_pack_version(
        pack_id=pid,
        version=ver,
        kind="curated",
        claim_eligible=False,
        scope="workspace",
        pack_hash=ph,
        object_types=["prompt"],
        workspace_id=wid,
        caller_workspace_id=wid,
        status="reviewed",
    )
    frozen = reg.freeze_pack_version(
        pack_id=pid,
        version=ver,
        scope="workspace",
        pack_hash=ph,
        workspace_id=wid,
        caller_workspace_id=wid,
        frozen_by="test",
    )
    assert str(frozen.get("kind") or "").lower() == "frozen"

    inv = subject_regression_inventory(workspace_id=wid, caller_workspace_id=wid)
    assert inv["claim_eligible"] is False
    assert inv["workspace_id"] == wid
    assert inv["workspace_promoted_count"] >= 1
    prompt = next(r for r in inv["subjects"] if r["subject_kind"] == "prompt")
    assert prompt["workspace_promoted"] is True
    na = (inv.get("next_action") or "").lower()
    assert "promot" in na  # promote / promoted / partial
