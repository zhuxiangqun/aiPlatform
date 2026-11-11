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
