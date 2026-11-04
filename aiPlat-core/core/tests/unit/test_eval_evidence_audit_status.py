"""Evidence audit status — hash checks; accuracy_claim always false."""
from __future__ import annotations

from core.apps.eval.service.evidence_audit import evidence_audit_status


def test_evidence_audit_status_verifies_tracked():
    st = evidence_audit_status(tenant_id="eval-v1")
    assert st["ok"] is True
    assert st["accuracy_claim"] is False
    assert st["process_split_authorized"] is False
    assert st["not_accuracy_certification"] is True
    assert st["dual_human_attestation"] == "confirmed"
    assert st["attestation_ok"] is True
    assert st["tracked_n"] >= 2
    assert st["tracked_ok_n"] == st["tracked_n"]
    assert st["required_for_feature_5_ok"] is True
    assert st["feature5_audit_ready"] is True
    # Worksheets may be absent (gitignored) → absent_ok is fine.
    assert st["worksheets_n"] >= 1


def test_eval_evidence_audit_status_facade():
    from core.api.core_facade import eval_evidence_audit_status

    st = eval_evidence_audit_status()
    assert st["accuracy_claim"] is False
    assert st["all_tracked_ok"] is True
