"""G2b pack status — facilitation facts; scoped claim mirrors attestation+aggregate."""
from __future__ import annotations

from core.apps.eval.service.g2b import g2b_pack_status


def test_g2b_pack_status_reads_n100_pack():
    st = g2b_pack_status(tenant_id="eval-v1")
    assert st["ok"] is True
    assert st["accuracy_claim"] is True
    assert st["not_accuracy_certification"] is False
    assert st["task_count"] == 100
    assert st["target_n"] == 100
    assert st["pack_ready"] is True
    # Dual-human closeout evidence is n=100; scoped claim accepted 2026-11-13.
    assert st["closeout_n"] == 100
    assert st["pending_dual_human"] == 0
    assert st["dual_human_complete"] is True
    assert st.get("kappa") is not None
    assert "prompt" in (st.get("families") or {})
    assert "scoped accuracy_claim=true" in str(st.get("note") or "")


def test_eval_g2b_pack_status_facade():
    from core.api.core_facade import eval_g2b_pack_status

    st = eval_g2b_pack_status()
    assert st["accuracy_claim"] is True
    assert st["task_count"] >= 30
