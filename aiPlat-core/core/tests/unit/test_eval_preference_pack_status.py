"""Preference pack status — facilitation facts; accuracy_claim always false."""
from __future__ import annotations

from core.apps.eval.service.preference import preference_pack_status


def test_preference_pack_status_reads_pairs():
    st = preference_pack_status(tenant_id="eval-v1")
    assert st["ok"] is True
    assert st["accuracy_claim"] is False
    assert st["not_accuracy_certification"] is True
    assert st["pairs_n"] == 32
    assert st["pack_ready"] is True
    # Committed aggregate has dual A/B labels for all 32 pairs.
    assert st["labeled_a"] == 32
    assert st["labeled_b"] == 32
    assert st["pending_a"] == 0
    assert st["pending_b"] == 0
    assert st["dual_human_complete"] is True
    assert st["fixture_solo"] is False
    assert st["preference_kappa"] is not None


def test_eval_preference_pack_status_facade():
    from core.api.core_facade import eval_preference_pack_status

    st = eval_preference_pack_status()
    assert st["accuracy_claim"] is False
    assert st["pairs_n"] >= 30
