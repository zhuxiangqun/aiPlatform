"""Scorecard honesty status — accuracy_claim / authorize always false."""
from __future__ import annotations

from core.apps.eval.service.scorecard import scorecard_status


def test_scorecard_status_reads_v1():
    st = scorecard_status(tenant_id="eval-v1")
    assert st["ok"] is True
    assert st["accuracy_claim"] is False
    assert st["process_split_authorized"] is False
    assert st["not_production_authorization"] is True
    assert st["dual_human_attestation"] == "confirmed"
    assert isinstance(st["axes"], list) and len(st["axes"]) >= 3
    assert st["dimensions_n"] >= 5
    # evidence_manifest.v1.json method.g2b_accuracy (n=100 closeout; claim=false)
    assert st["g2b_closeout_n"] == 100
    assert st["g2b_target_n"] == 100


def test_eval_scorecard_status_facade():
    from core.api.core_facade import eval_scorecard_status

    st = eval_scorecard_status()
    assert st["accuracy_claim"] is False
    assert st["process_split_authorized"] is False
