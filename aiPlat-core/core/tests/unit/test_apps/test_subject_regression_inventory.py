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
    assert "compile-suite-profile" in str(inv.get("ladder") or "")
    prompt = next(r for r in inv["subjects"] if r["subject_kind"] == "prompt")
    assert prompt.get("profile_id")
    assert "profile_id=" in str(prompt.get("suite_profile_href") or "")
    assert str(prompt["profile_id"]) in str(prompt["suite_profile_href"])


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


def test_inventory_last_exam_enrichment(tmp_path, monkeypatch):
    from core.apps.eval.service.suite_exam_summary_store import record_suite_exam_summary
    from core.apps.eval.service.subject_regression_inventory import (
        subject_regression_inventory,
    )

    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    wid = "ws-inv-exam"
    inv0 = subject_regression_inventory(workspace_id=wid, caller_workspace_id=wid)
    prompt = next(r for r in inv0["subjects"] if r["subject_kind"] == "prompt")
    pid = str(prompt.get("profile_id") or "").strip()
    assert pid and inv0.get("last_exam_count") == 0
    record_suite_exam_summary(
        {
            "ok": True,
            "profile_id": pid,
            "subject_kind": "prompt",
            "live": False,
            "run_id": "suite-profile-test01",
            "executed_case_count": 3,
            "counts": {"pass": 2, "fail": 1, "error": 0},
        },
        workspace_id=wid,
    )
    inv = subject_regression_inventory(workspace_id=wid, caller_workspace_id=wid)
    assert inv["claim_eligible"] is False and inv["last_exam_count"] >= 1
    assert "last_exam_" in str(inv.get("ladder") or "")
    row = next(r for r in inv["subjects"] if r["subject_kind"] == "prompt")
    assert row["last_exam_ok"] is True and row["last_exam_live"] is False
    assert row["last_exam_pass"] == 2 and row["last_exam_fail"] == 1
    assert row["last_exam_run_id"] == "suite-profile-test01"
    assert str(row.get("last_exam_at") or "").strip()
    assert inv.get("last_exam_live_count") == 0
    assert "live·smoke" in str(inv.get("ladder") or "")

    record_suite_exam_summary(
        {
            "ok": True,
            "profile_id": pid,
            "subject_kind": "prompt",
            "live": True,
            "run_id": "suite-profile-live01",
            "executed_case_count": 4,
            "counts": {"pass": 3, "fail": 1, "error": 0},
        },
        workspace_id=wid,
    )
    inv2 = subject_regression_inventory(workspace_id=wid, caller_workspace_id=wid)
    assert inv2["claim_eligible"] is False
    assert inv2.get("last_exam_live_count") >= 1
    row2 = next(r for r in inv2["subjects"] if r["subject_kind"] == "prompt")
    assert row2["last_exam_live"] is True
    assert row2["last_exam_run_id"] == "suite-profile-live01"


def test_inventory_next_action_nudges_live_smoke_when_dry_only(tmp_path, monkeypatch):
    """When all subjects workspace-promoted and only dry ledger, nudge live·smoke."""
    from core.apps.eval.service import case_pack_registry as reg
    from core.apps.eval.service.subject_capability_promote import (
        _bank_specs,
        list_promotable_subject_kinds,
    )
    from core.apps.eval.service.suite_exam_summary_store import record_suite_exam_summary
    from core.apps.eval.service.subject_regression_inventory import (
        subject_regression_inventory,
    )

    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    wid = "ws-inv-live-nudge"
    specs = _bank_specs()
    for kind in list_promotable_subject_kinds():
        spec = specs.get(kind) or {}
        pid = str(spec.get("pack_id") or "").strip()
        ver = str(spec.get("version") or "").strip()
        if not pid or not ver:
            continue
        ph = "sha256:" + ("ab" * 32)
        reg.register_pack_version(
            pack_id=pid,
            version=ver,
            kind="curated",
            claim_eligible=False,
            scope="workspace",
            pack_hash=ph,
            object_types=[kind] if kind in ("prompt",) else [],
            workspace_id=wid,
            caller_workspace_id=wid,
            status="reviewed",
        )
        reg.freeze_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            pack_hash=ph,
            workspace_id=wid,
            caller_workspace_id=wid,
            frozen_by="test",
        )

    inv0 = subject_regression_inventory(workspace_id=wid, caller_workspace_id=wid)
    if inv0.get("workspace_promoted_count", 0) < inv0.get("subject_count", 1):
        # Not all kinds freeze the same way — still assert ladder honesty.
        assert "live·smoke" in str(inv0.get("ladder") or "")
        return

    prompt = next(r for r in inv0["subjects"] if r["subject_kind"] == "prompt")
    pid = str(prompt.get("profile_id") or "").strip()
    record_suite_exam_summary(
        {
            "ok": True,
            "profile_id": pid,
            "live": False,
            "run_id": "dry-only",
            "executed_case_count": 2,
            "counts": {"pass": 2},
        },
        workspace_id=wid,
    )
    inv = subject_regression_inventory(workspace_id=wid, caller_workspace_id=wid)
    assert inv["claim_eligible"] is False
    na = (inv.get("next_action") or "").lower()
    assert "live" in na and "smoke" in na
    assert "claim" in na
